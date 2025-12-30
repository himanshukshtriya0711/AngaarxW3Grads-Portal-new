from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import time, json
import requests
from django.core.paginator import Paginator
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

import base64
import re

from accounts.models import Student
from .models import RecommendedQuestions

from django.views.decorators.cache import cache_control

from .models import Sheet, Question, TestCase, Submission, DriverCode, Streak

# Judge0 API endpoint and key
JUDGE0_URL = "https://theangaarbatch.in/judge0/submissions"
# JUDGE0_URL = "https://judge0-ce.p.rapidapi.com/submissions/"

HEADERS = {
    # "X-RapidAPI-Key": "2466ab7710mshe96d45a19b806efp1a790ajsne8eeb32a6197",  # Replace with your actual API key
    "X-RapidAPI-Host": "98.83.136.105:2358",
    # "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
    "Content-Type": "application/json"
}


def execute_code(request):
    print("🛠️ execute_code called")
    
    if request.method == 'POST':
        
        language_id = request.POST.get('language_id')
        source_code = request.POST.get('source_code')
        input_data = request.POST.get('input_data')  # Get input data from the request
        
        # Ensure required fields are provided
        if not (language_id and source_code):
            return JsonResponse({"error": "Missing required fields (language_id, source_code)"}, status=400)

        # Encode source code and input data
        encoded_code = base64.b64encode(source_code.encode('utf-8')).decode('utf-8')
        encoded_input = base64.b64encode(input_data.encode('utf-8')).decode('utf-8') if input_data else None

        # Prepare submission payload
        data = {
            "source_code": encoded_code,
            "language_id": language_id,
            "cpu_time_limit": 1,
            "cpu_extra_time": 1,
            "base64_encoded": True,
            "stdin": encoded_input  # Add input data to the payload
        }

        if language_id in ['50', '54']:  # C, C++, Java
            data["compiler_options"] = "-lm"

        try:
            response = requests.post(f"{JUDGE0_URL}?base64_encoded=true", json=data, headers=HEADERS, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return JsonResponse({"error": f"Request failed: {str(e)}"}, status=500)

        if response.status_code == 201:
            token = response.json().get('token')
            
            if not token:
                return JsonResponse({"error": "Failed to retrieve submission token"}, status=500)

            for i in range(10):  # Maximum of 10 attempts
                try:
                    result_response = requests.get(f"{JUDGE0_URL}/{token}?base64_encoded=true", headers=HEADERS, timeout=10)
                    result_response.raise_for_status()
                    result = result_response.json()
                except requests.exceptions.RequestException as e:
                    return JsonResponse({"error": f"Polling failed: {str(e)}"}, status=500)

                status_id = result.get('status', {}).get('id')
                status_description = result.get('status', {}).get('description', 'Unknown Status')

                if status_id == 3:  # ✅ Accepted (Successful Execution)
                    output = result.get('stdout')
                    if output:
                        decoded_output = base64.b64decode(output).decode('utf-8')
                        return JsonResponse({"output": decoded_output, "status": status_description})

                elif status_id in [5, 6, 7, 11]:  # ❌ Error Cases
                    error_output = (
                        result.get('stderr') or
                        result.get('compile_output') or
                        result.get('message')
                    )
                    if error_output:
                        decoded_error = base64.b64decode(error_output).decode('utf-8', errors='replace')
                        return JsonResponse({"error": decoded_error, "status": status_description})
    
                time.sleep(1)  # Poll every 1 second

            return JsonResponse({"error": "Timeout while waiting for the result"}, status=408)

        return JsonResponse({"error": "Failed to submit code to Judge0"}, status=response.status_code)

    return JsonResponse({"error": "Invalid request method"}, status=405)

# =====================================================================================================
# ========================================= HELPER FUNCTIONS ==========================================
# =====================================================================================================
def normalize_output(output):
    """
    Normalize output for consistent comparison by stripping extra spaces
    and normalizing newline characters.
    """
    
    # print("\nOUTPUT IN NORMALIZE FUNCTION:", output)
        
    if not output:
        return ""
    return output.replace("\r\n", "\n").strip()

# ==========================================

def get_test_cases(question):
    """
    Get all test cases associated with the question.
    """
    try:
        return question.test_cases.all()
    except Exception as e:
        print(f"Error fetching test cases: {e}")
        return []


def create_submission(user, question, source_code, language_id, passed, total, total_submission_count):
    """
    Create a new submission entry in the database.
    """
    
    status = 'Accepted' if passed == total else 'Wrong Answer'
    
     # update streaks
    if status == 'Accepted':
        update_user_streak(user)

    score = int(((passed / total) * 100) * (1 - 0.1 * (total_submission_count - 1)))
    
    if score < 0:
        score = 0
        
    score = score
    
    update_coin(user, score, question)
        
    try:
        submission = Submission.objects.create(
            user = user,
            question = question,
            code = source_code,
            language = language_id,
            status = status,score = score
        )
        
        submission.save()
        
        return submission
        
    except Exception as e:
        print(f"Error creating submission: {e}")
        raise Exception("Could not create submission.")


def process_test_case_result(inputs, outputs, expected_outputs):

    
    results = []
    for input_data, expected_output, output in zip(inputs, expected_outputs, outputs):
        result = {
            "input": input_data,
            "expected_output": expected_output,
            "user_output": output,
            "passed": output == expected_output,
            "status": "Passed" if output == expected_output else "Wrong Answer"
        }
        results.append(result)
    return results


@login_required(login_url="login")
def problem(request, slug):
    """
    Render the problem page with question details and sample test cases.
    """
    try:
        # Fetch from database
        question = get_object_or_404(Question, slug=slug)
        
        # Check if sheet is enabled
        sheet = Sheet.objects.filter(questions=question, is_approved=True).first()

        if sheet and not sheet.is_enabled:
            messages.info(request, "This question is in the sheet which is disabled now. Try Later.")
            return redirect('my_batches')
        
        if sheet and sheet.is_sequential:
            # Get all enabled questions for the user
            enabled_questions = sheet.get_enabled_questions_for_user(request.user)
            
            # Check if the question is enabled for the user
            if question not in enabled_questions:
                messages.info(request, "Beta jb tu paida nhi hua tha tb m URL se khelta tha. Mehnt kr 🙂")
                return redirect('my_sheet', slug=sheet.slug)
                
        # Process markdown in problem statement
        if question.scenario:
            question.scenario = convert_backticks_to_code(question.scenario)
        question.description = convert_backticks_to_code(question.description)
        
        # Get sample test cases
        sample_test_cases = TestCase.objects.filter(question=question, is_sample=True)
        
        # Prepare context
        context = {
            'question': question,
            'sample_test_cases': sample_test_cases,
            'sheet': sheet
        }
        
        return render(request, 'practice/problem.html', context)
        
    except Exception as e:
        print(f"Error loading problem page: {e}")
        messages.error(request, f"Error loading problem: {str(e)}")
        return redirect('my_sheet', slug=sheet.slug if sheet else 'my_batches')

# ============================================ UPDATE COINS ===============================================

def update_coin(user, score, question):
    
    # update the coins only if the user has submitted the code for the first time successfully
    if Submission.objects.filter(user=user, question=question, status="Accepted").count() > 1:
        return
    
    if score == 100:
        user.coins += 5
    elif score >= 75:
        user.coins += 4
    elif score >= 50:
        user.coins += 3
    elif score >= 25:
        user.coins += 2
    else:
        user.coins += 1
    user.save()

# ============================================ UPDATE STREAKS =============================================

def update_user_streak(user):
    """
    Update user streak for successful coding question submission.
    This function maintains backward compatibility while using the new unified system.
    """
    # Use the new class method from Streak model
    Streak.update_user_streak(user)


def run_code_result(request, token, slug):
    """
    Process results for sample test cases only.
    This endpoint is separate from send_output to handle run_code operations differently from submit_code.
    """
    try:
        print("Entering run_code_result function with token:", token)
        question = get_object_or_404(Question, slug=slug)
        
        # Get the Judge0 result using the token
        start = time.time()
        judge0_response = get_result(token)
        end = time.time()
        print("Time to get Judge0 result:", end - start)
        
        # Handle errors (compilation errors, runtime errors, etc.)
        if judge0_response.get("error") or judge0_response.get("compile_output") or judge0_response.get("stderr"):
            print("Error in Judge0 response for run_code_result:", 
                 judge0_response.get("error"), 
                 judge0_response.get("compile_output"), 
                 judge0_response.get("stderr"))
            
            return JsonResponse({
                "error": judge0_response.get("error"),
                "error_details": judge0_response.get("error_details"),
                "stderr": judge0_response.get("stderr"),
                "compile_output": judge0_response.get("compile_output"),
                "status_description": judge0_response.get("status_description"),
                "time_limit_exceeded": judge0_response.get("time_limit_exceeded"),
                "token": token
            })
        
        # Get ONLY sample test cases
        sample_test_cases = TestCase.objects.filter(question=question, is_sample=True)
        outputs = judge0_response.get("outputs", [])
        
        if not outputs:
            return JsonResponse({
                "error": "No outputs generated",
                "token": token
            })
        
        # Process test case results for sample cases only
        inputs = [tc.input_data for tc in sample_test_cases]
        expected_outputs = [normalize_output(tc.expected_output) for tc in sample_test_cases]
        
        # Handle case where number of outputs doesn't match test cases
        if len(outputs) != len(expected_outputs):
            print(f"Warning: Output count mismatch in run_code_result. Expected {len(expected_outputs)}, got {len(outputs)}")
            # Pad or truncate outputs to match expected count
            if len(outputs) < len(expected_outputs):
                outputs.extend(["No output"] * (len(expected_outputs) - len(outputs)))
            else:
                outputs = outputs[:len(expected_outputs)]
        
        # Process the results
        test_case_results = process_test_case_result(inputs, outputs, expected_outputs)
        passed_test_cases = sum(1 for result in test_case_results if result['passed'])
        
        # Create the response WITHOUT creating a submission record
        result = {
            "status": "Success",
            "test_case_results": test_case_results,
            "is_all_test_cases_passed": passed_test_cases == len(test_case_results),
            "is_run_code": True,  # Flag to indicate this is a run_code result
            "summary": {
                "passed_count": passed_test_cases,
                "total": len(test_case_results)
            },
            "token": token
        }
        
        # Add execution metrics if available
        if judge0_response.get("execution_time"):
            result["execution_time"] = judge0_response.get("execution_time")
        
        if judge0_response.get("memory_used"):
            result["memory_used"] = judge0_response.get("memory_used")
        
        return JsonResponse(result)
        
    except Exception as e:
        print(f"Error in run_code_result: {e}")
        return JsonResponse({
            "error": "Error processing run results", 
            "error_details": str(e),
            "token": token
        }, status=500)

# ==========================================================================================================
# ====================================== Return Token =============================
# ==========================================================================================================

def return_token(question, source_code, language_id, test_cases, cpu_time_limit, memory_limit):
    """
    Submit code to Judge0 and return a token for tracking the submission.
    Optimized for high concurrency with caching and connection pooling.
    """
    print("Entering the return token function")
    
    # Check for cached driver code first
    driver_code_key = None
    if not question.show_complete_driver_code:
        driver_code_key = f"driver_code_{question.id}_{language_id}"
        cached_driver_code = cache.get(driver_code_key)
        
        if cached_driver_code:
            source_code = cached_driver_code.replace("#USER_CODE#", source_code)
        else:
            driver_code = DriverCode.objects.filter(question=question, language_id=language_id).first()
            if driver_code:
                # Cache driver code for 1 hour
                cache.set(driver_code_key, driver_code.complete_driver_code, 3600)
                source_code = driver_code.complete_driver_code.replace("#USER_CODE#", source_code)
            else:
                return {"error": "Driver code not found for this language.", "outputs": None, "token": None}
    
    # Generate a cache key based on code content and test cases
    # This allows us to return the same token for identical submissions
    code_hash = hash(source_code)
    test_cases_hash = hash(tuple((tc.id, tc.input_data) for tc in test_cases))
    cache_key = f"judge0_token_{question.id}_{language_id}_{code_hash}_{test_cases_hash}"
    
    # Check if we already have a token for this exact submission
    cached_token = cache.get(cache_key)
    if cached_token:
        print(f"✅ Using cached token: {cached_token}")
        return cached_token

    # Prepare single stdin batch input for Judge0
    stdin = f"{len(test_cases)}~"
    for test_case in test_cases:
        stdin += f"{test_case.input_data}~"

    # Convert "~" to newline "\n" before encoding
    stdin = stdin.replace("~", "\n")  
    
    # Encode code and stdin
    try:
        encoded_code = base64.b64encode(source_code.encode('utf-8')).decode('utf-8')
        encoded_stdin = base64.b64encode(stdin.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"❌ Encoding error: {e}")
        return {"error": f"Encoding error: {str(e)}", "outputs": None, "token": None}

    submission_data = {
        "source_code": encoded_code,
        "language_id": language_id,
        "stdin": encoded_stdin,
        "cpu_time_limit": cpu_time_limit,
        "wall_time_limit": cpu_time_limit,
        "memory_limit": memory_limit * 1000,
        "enable_per_process_and_thread_time_limit": True,
        "base64_encoded": True
    }

    # Use a session for connection pooling
    session = requests.Session()
    
    try:
        # Submit code to Judge0 with retries for resilience
        for attempt in range(3):  # Try up to 3 times
            try:
                response = session.post(
                    JUDGE0_URL + "?base64_encoded=true", 
                    json=submission_data, 
                    headers=HEADERS, 
                    timeout=10
                )
                response.raise_for_status()
                
                token = response.json().get("token")
                if token:
                    # Cache the token for 10 minutes
                    cache.set(cache_key, token, 600)
                    print(f"✅ TOKEN: {token}")
                    return token
                
                # If we got a response but no token, wait briefly and retry
                time.sleep(0.5)
            except (requests.RequestException, ValueError) as e:
                print(f"❌ Attempt {attempt+1} failed: {e}")
                if attempt == 2:  # Last attempt
                    raise
                time.sleep(1)  # Wait before retrying
        
        return {"error": "No token received from Judge0 after multiple attempts.", "outputs": None, "token": None}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return {"error": f"Request error: {str(e)}", "outputs": None, "token": None}
    except ValueError as e:
        print(f"❌ JSON parsing error: {e}")
        return {"error": f"JSON parsing error: {str(e)}", "outputs": None, "token": None}
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return {"error": f"Unexpected error: {str(e)}", "outputs": None, "token": None}
    finally:
        session.close()

# =============================================== GET RESULT ================================================
import asyncio
import concurrent.futures
from functools import wraps

# ThreadPoolExecutor for running async code in sync contexts
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def run_async_in_thread(async_func):
    """Decorator to run an async function in a thread pool, making it callable from sync code."""
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(async_func(*args, **kwargs))
        except Exception as e:
            print(f"Error running async function in thread: {e}")            
        finally:
            loop.close()
    return wrapper

async def get_result_async(token):
    """
    Asynchronous version of get_result - get code execution result from Judge0 with detailed error information.
    """
    print("Entering async fetching output from judge0")
    
    try:
        # Use httpx for async HTTP requests (fallback to sync if needed)
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                result_response = await client.get(
                    f"{JUDGE0_URL}/{token}?base64_encoded=true", 
                    headers=HEADERS, 
                    timeout=10
                )
                result = result_response.json()
        except ImportError:
            # Fallback to requests in a thread if httpx is not available
            with concurrent.futures.ThreadPoolExecutor() as executor:
                loop = asyncio.get_event_loop()
                def fetch():
                    return requests.get(
                        f"{JUDGE0_URL}/{token}?base64_encoded=true", 
                        headers=HEADERS, 
                        timeout=10
                    ).json()
                result = await loop.run_in_executor(executor, fetch)
        
        # Create a base result dictionary with token
        result_dict = {"token": token}
        
        # Add status information
        if result.get("status"):
            status_id = result["status"].get("id")
            status_description = result["status"].get("description")
            result_dict["status_id"] = status_id
            result_dict["status_description"] = status_description
        
        # Process stderr if present
        if result.get("stderr"):
            stderr = base64.b64decode(result['stderr']).decode('utf-8', errors='replace')
            print("❌ STDERR:", stderr)
            result_dict["stderr"] = stderr
            result_dict["error"] = f"Runtime Error"
        
        # Process compile output if present
        if result.get("compile_output"):
            compile_output = base64.b64decode(result['compile_output']).decode('utf-8', errors='replace')
            print("❌ COMPILE OUTPUT:", compile_output)
            result_dict["compile_output"] = compile_output
            result_dict["error"] = f"Compilation Error"
        
        # Handle specific status codes
        if result.get("status", {}).get("id") == 5:  # Time Limit Exceeded
            result_dict["error"] = "Time Limit Exceeded (TLE)"
            result_dict["time_limit_exceeded"] = True
            
        elif result.get("status", {}).get("id") == 6:  # Compilation Error
            result_dict["error"] = "Compilation Error"
            
        # Add memory and time usage information
        if result.get("memory"):
            result_dict["memory_used"] = result["memory"]
            
        if result.get("time"):
            result_dict["execution_time"] = result["time"]
        
        # Process stdout if present
        outputs = result.get("stdout", "")
        if outputs:
            try:
                outputs = base64.b64decode(outputs).decode('utf-8', errors='replace')
                outputs = [output.strip() for output in outputs.split("~") if output.strip()]
                result_dict["outputs"] = outputs
            except Exception as decode_error:
                print(f"Error decoding outputs: {decode_error}")
                result_dict["error"] = f"Error decoding outputs: {str(decode_error)}"
                result_dict["outputs"] = ["Error decoding output"]
        else:
            result_dict["outputs"] = ["No output generated."]
        
        return result_dict
        
    except Exception as e:
        print(f"Async Error: {e}")
        return {
            "error": f"Request Error", 
            "error_details": str(e),
            "outputs": None, 
            "token": token
        }

def get_result(token):
    """
    Get the result of a code execution from Judge0 with detailed error information.
    This function can be called from synchronous code and maintains backward compatibility.
    """
    print("Entering the fetching output from judge0")
    
    try:
        # Try to use the async version running in a thread
        try:
            return run_async_in_thread(get_result_async)(token)
        except Exception as async_error:
            print(f"Async execution failed, falling back to sync: {async_error}")
            # Fall back to the original synchronous implementation
            # Poll Judge0 for results
            result_response = requests.get(f"{JUDGE0_URL}/{token}?base64_encoded=true", headers=HEADERS, timeout=10)
            result = result_response.json()
            
            # Create a base result dictionary with token
            result_dict = {"token": token}
            
            # Add status information
            if result.get("status"):
                status_id = result["status"].get("id")
                status_description = result["status"].get("description")
                result_dict["status_id"] = status_id
                result_dict["status_description"] = status_description
            
            # Process stderr if present
            if result.get("stderr"):
                stderr = base64.b64decode(result['stderr']).decode('utf-8', errors='replace')
                print("❌ STDERR:", stderr)
                result_dict["stderr"] = stderr
                result_dict["error"] = f"Runtime Error"
            
            # Process compile output if present
            if result.get("compile_output"):
                compile_output = base64.b64decode(result['compile_output']).decode('utf-8', errors='replace')
                print("❌ COMPILE OUTPUT:", compile_output)
                result_dict["compile_output"] = compile_output
                result_dict["error"] = f"Compilation Error"
            
            # Handle specific status codes
            if result.get("status", {}).get("id") == 5:  # Time Limit Exceeded
                result_dict["error"] = "Time Limit Exceeded (TLE)"
                result_dict["time_limit_exceeded"] = True
                
            elif result.get("status", {}).get("id") == 6:  # Compilation Error
                result_dict["error"] = "Compilation Error"
                
            # Add memory and time usage information
            if result.get("memory"):
                result_dict["memory_used"] = result["memory"]
                
            if result.get("time"):
                result_dict["execution_time"] = result["time"]
            
            # Process stdout if present
            outputs = result.get("stdout", "")
            if outputs:
                try:
                    outputs = base64.b64decode(outputs).decode('utf-8', errors='replace')
                    outputs = [output.strip() for output in outputs.split("~") if output.strip()]
                    result_dict["outputs"] = outputs
                except Exception as decode_error:
                    print(f"Error decoding outputs: {decode_error}")
                    result_dict["error"] = f"Error decoding outputs: {str(decode_error)}"
                    result_dict["outputs"] = ["Error decoding output"]
            else:
                result_dict["outputs"] = ["No output generated."]
            
            return result_dict
        
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {
            "error": f"Request Error", 
            "error_details": str(e),
            "outputs": None, 
            "token": token
        }
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return {
            "error": f"Unexpected Error", 
            "error_details": str(e),
            "outputs": None, 
            "token": token
        }

# =============================================== SEND OUTPUT ============================================

def send_output(request, token, slug):
    """
    Process the output from Judge0 and return formatted results to the client.
    Handles both successful executions and various error conditions.
    """
    judge0_response = None  # Initialize to avoid reference errors in exception handlers
    
    try: 
        print("TOKEN ON SEND OUTPUT:", token)
        
        question = get_object_or_404(Question, slug=slug)
        user = request.user.student            
        
        body = json.loads(request.body)
        
        source_code = body.get('source_code')
        language_id = body.get('language_id')
        token = body.get('token')
        
        if not token or not source_code or not language_id:
            return JsonResponse({
                "error": "Missing required parameters",
                "error_details": "Token, source code, and language ID are required."
            }, status=400)
        
        print("Processing submission with token:", token)
        
        test_cases = get_test_cases(question)
        if not test_cases:
            return JsonResponse({
                "error": "No test cases found for this question",
                "token": token
            }, status=400)
    
        # Get result from Judge0
        start = time.time()
        judge0_response = get_result(token)
        end = time.time()
        
        print("Time Taken to get Output:", end - start)
        print("Judge0 Response:", judge0_response)
                    
        # Handle error cases
        if judge0_response.get("error") or judge0_response.get("compile_output") or judge0_response.get("stderr"):
            # Return all error information to the client for detailed display
            
            print("Error in Judge0 response:", judge0_response.get("error"), judge0_response.get("compile_output"), judge0_response.get("stderr"))
            
            return JsonResponse({
                "error": judge0_response.get("error"),
                "error_details": judge0_response.get("error_details"),
                "stderr": judge0_response.get("stderr"),
                "compile_output": judge0_response.get("compile_output"),
                "status_description": judge0_response.get("status_description"),
                "time_limit_exceeded": judge0_response.get("time_limit_exceeded"),
                "token": judge0_response.get("token")
            })

        # Process successful outputs
        outputs = judge0_response.get("outputs", [])
        if not outputs:
            return JsonResponse({
                "error": "No output generated",
                "token": judge0_response.get("token")
            })
        
        # Prepare test case results
        try:
            expected_outputs = [normalize_output(tc.expected_output) for tc in test_cases]
            inputs = [tc.input_data for tc in test_cases]
            
            # Handle case where number of outputs doesn't match test cases
            if len(outputs) != len(expected_outputs):
                print(f"Warning: Output count mismatch. Expected {len(expected_outputs)}, got {len(outputs)}")
                # Pad or truncate outputs to match expected count
                if len(outputs) < len(expected_outputs):
                    outputs.extend(["No output"] * (len(expected_outputs) - len(outputs)))
                else:
                    outputs = outputs[:len(expected_outputs)]
            
            test_case_results = process_test_case_result(inputs, outputs, expected_outputs)
            passed_test_cases = sum(1 for result in test_case_results if result['passed'])
            
            # Get submission count for score calculation
            total_submission_count = Submission.objects.filter(user=user, question=question).count()            
            
            # Create a submission record
            submission = create_submission(user, question, source_code, language_id, passed_test_cases, len(test_cases), total_submission_count)
            
            # Add execution metrics if available
            result = {
                "test_case_results": test_case_results,
                "status": submission.status,
                "score": submission.score,
                "token": judge0_response.get("token"),
                "is_all_test_cases_passed": passed_test_cases == len(test_cases)
            }
            
            # Add execution time and memory if available
            if judge0_response.get("execution_time"):
                result["execution_time"] = judge0_response.get("execution_time")
                
            if judge0_response.get("memory_used"):
                result["memory_used"] = judge0_response.get("memory_used")
                
            return JsonResponse(result)
            
        except Exception as process_error:
            print(f"Error processing test results: {process_error}")
            return JsonResponse({
                "error": "Error processing test results",
                "error_details": str(process_error),
                "token": judge0_response.get("token") if judge0_response else token
            })

    except Question.DoesNotExist:
        return JsonResponse({
            "error": "Question not found",
            "token": token
        }, status=404)
    except json.JSONDecodeError as json_error:
        print(f"JSON decode error: {json_error}")
        return JsonResponse({
            "error": "Invalid request format",
            "error_details": "The request body could not be parsed as JSON"
        }, status=400)
    except Exception as e:
        print(f"Error in send_output: {e}")
        return JsonResponse({
            "error": "Server error",
            "error_details": str(e),
            "token": judge0_response.get("token") if judge0_response else token
        }, status=500)  # Return 500 for server errors


    

# ============================================ SUBMIT CODE ===============================================

@csrf_exempt
def submit_code(request, slug):
    """
    Handle user code submission for a problem with optimizations for high concurrency.
    Includes rate limiting and caching to prevent system overload.
    """
    if request.method == 'POST':      
        try:
            # Get user info
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required."}, status=401)
                
            user = request.user.student
            
            # Validate inputs
            question = get_object_or_404(Question, slug=slug)
            language_id = request.POST.get('language_id')
            source_code = request.POST.get('submission_code')
            
            if not language_id or not source_code:
                return JsonResponse({"error": "Missing language ID or source code."}, status=400)


            # Get test cases with caching
            test_cases_key = f"test_cases_{question.id}"
            test_cases = cache.get(test_cases_key)
            
            if not test_cases:
                test_cases = get_test_cases(question)
                if test_cases:
                    # Cache test cases for 1 hour
                    cache.set(test_cases_key, test_cases, 3600)
            
            if not test_cases:
                return JsonResponse({"error": "No test cases available for this question."}, status=400)

            # Check if sheet is enabled (with caching)
            sheet_key = f"sheet_status_{question.id}"
            sheet_status = cache.get(sheet_key)
            
            if sheet_status is None:
                sheet = Sheet.objects.filter(questions=question, is_approved=True).first()
                sheet_status = sheet and not sheet.is_enabled
                cache.set(sheet_key, sheet_status, 300)  # Cache for 5 minutes

            if sheet_status:
                return JsonResponse({"sheet_disabled": "Sheet not enabled."}, status=400)

            # Run the code and process results
            start = time.time()
            token = return_token(question, source_code, language_id, test_cases, question.cpu_time_limit, question.memory_limit)
            end = time.time()
            
            print("Time Taken to get token:", end - start)
            
            return JsonResponse({
                "token": token,
                "source_code": source_code
            })
        
        except Exception as e:
            print("Exception occurred:", e)
            return JsonResponse({
                "error": str(e)
            }, status=500)
    
    else:
        return JsonResponse({"error": "Invalid request method."}, status=400)


# ============================================== DRIVER CODE FETCHING ===============================================

def get_driver_code(request, question_id, language_id):
    question = get_object_or_404(Question, id=question_id)
    driver_code = DriverCode.objects.filter(question_id=question_id, language_id=language_id).first()    
    if driver_code:
        
        if question.show_complete_driver_code:
            code = driver_code.complete_driver_code.replace("#USER_CODE#", driver_code.visible_driver_code)
            return JsonResponse({"success": True, "code": code})
        
        elif driver_code.visible_driver_code == "1":
            return JsonResponse({"success": True, "code": driver_code.complete_driver_code})
        
        else:
            return JsonResponse({"success": True, "code": driver_code.visible_driver_code})
        
        return JsonResponse({"success": True, "code": driver_code.visible_driver_code})
    return JsonResponse({"success": False, "message": "Driver code not found.", "language id": language_id, "question id": question_id}, status=404)

# ========================================== RUN CODE AGAINST SAMPLE TEST CASES ==========================================

@csrf_exempt
def run_code(request, slug):
    """Run code on sample test cases only (without creating a submission record)
    This function returns a token that the client can use to poll Judge0 directly.
    """
    if request.method == 'POST':
        try:
            # Get question and user info
            question = get_object_or_404(Question, slug=slug)
            
            # Parse request data
            data = json.loads(request.body)
            language_id = data.get('language_id')
            source_code = data.get('code')   
            
            print("Source Code in Run Function:", source_code[:100], "...")

            if not language_id or not source_code:
                return JsonResponse({"error": "Missing language ID or source code."}, status=400)

            # Fetch ONLY sample test cases
            sample_test_cases = TestCase.objects.filter(question=question, is_sample=True)
            if not sample_test_cases:
                return JsonResponse({"error": "No sample test cases available."}, status=400)

            # Check if sheet is enabled (with caching)
            sheet_key = f"sheet_status_{question.id}"
            sheet_status = cache.get(sheet_key)
            
            if sheet_status is None:
                sheet = Sheet.objects.filter(questions=question, is_approved=True).first()
                sheet_status = sheet and not sheet.is_enabled
                cache.set(sheet_key, sheet_status, 300)  # Cache for 5 minutes

            if sheet_status:
                return JsonResponse({"sheet_disabled": "Sheet not enabled."}, status=400)

            # Submit code to Judge0 and get token only
            token = return_token(question, source_code, language_id, sample_test_cases, question.cpu_time_limit, question.memory_limit)
            
            if isinstance(token, dict) and token.get("error"): 
                # Handle error in token generation
                return JsonResponse({
                    "error": token.get("error"),
                    "outputs": None
                }, status=400)

            # Return the token to the client
            # The client will poll Judge0 directly and fetch results when done
            print(f"Run code: Generated token {token} for sample test cases")
            return JsonResponse({
                "token": token,
                "status": "Token generated"
            })

        except Question.DoesNotExist:
            return JsonResponse({"error": "Question not found."}, status=404)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body."}, status=400)
        except Exception as e:
            print(f"Error in run_code: {e}")
            return JsonResponse({
                "error": "Server error",
                "error_details": str(e)
            }, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=400)

# ========================================== CUSTOM INPUT ==========================================

def custom_input(request, slug):
    # if request.method == 'POST':
    #     question = get_object_or_404(Question, slug=slug)
        
    #     data = json.loads(request.body)
        
    #     language_id = data.get('language_id')
    #     source_code = data.get('code')
    #     input_data = data.get('input')
        
    #     if not language_id or not source_code or not input_data:
    #         return JsonResponse({"error": "Missing language ID, source code, or input data."}, status=400)
        
    #     # Split the input into lines
    #     input_lines = input_data.strip().split('\n')
        
    #     try:
    #         num_test_cases = int(input_lines[0])
    #         test_case_inputs = input_lines[1:num_test_cases + 1]
    #     except (ValueError, IndexError):
    #         return JsonResponse({"error": "Invalid input format. The first line should indicate the number of test cases."}, status=400)
        
    #     if len(test_case_inputs) != num_test_cases:
    #         return JsonResponse({"error": "Number of provided inputs does not match the specified number of test cases."}, status=400)
        
    #     # Create test cases
    #     test_cases = [
    #         TestCase(question=question, input_data=tc_input, expected_output="")
    #         for tc_input in test_case_inputs
    #     ]
        
    #     # Run code on Judge0
    #     judge0_response = run_code_on_judge0(
    #         question,
    #         source_code,
    #         language_id,
    #         test_cases,
    #         question.cpu_time_limit,
    #         question.memory_limit
    #     )
        
    #     if judge0_response.get("error") or judge0_response.get("compile_output"):  # Any Kind of Error
    #         result = {
    #             "error": judge0_response.get("error"),
    #             "token": judge0_response.get("token")
    #         }
    #         if judge0_response.get("compile_output"):
    #             result["compile_output"] = judge0_response.get("compile_output")
    #         return JsonResponse(result, status=400)
        
    #     outputs = judge0_response["outputs"]
        
    #     # Set expected outputs if not already set
    #     for i, test_case in enumerate(test_cases):
    #         if test_case.expected_output == "":
    #             test_case.expected_output = outputs[i]
        
    #     results = [
    #         {
    #             "input": test_case.input_data,
    #             "expected_output": test_case.expected_output
    #         }
    #         for test_case in test_cases
    #     ]
        
    #     return JsonResponse({
    #         "status": "Success",
    #         "test_case_results": results
    #     })
        
    return JsonResponse({"error": "Invalid request method."}, status=400)

# ================================== UNLOCK HINT ==================================================

def unlock_hint(request, question_id):
    if request.method == 'POST' and request.user.is_authenticated:
        question = get_object_or_404(Question, id=question_id)
        student = request.user.student

        if question.hint:  # Check if the question has a hint
            if student.coins > 0:  # Check if the user has enough coins
                student.coins -= 5  # Deduct a spark
                student.save()
                return JsonResponse({'status': 'success', 'hint': question.hint})
            else:
                return JsonResponse({'status': 'error', 'message': 'Not enough coins'})
        else:
            return JsonResponse({'status': 'error', 'message': 'No hint available for this question'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

# ========================================== NEXT QUESTION ==========================================

@login_required(login_url="login")
def render_next_question_in_sheet(request, sheet_id, question_id):
    sheet = get_object_or_404(Sheet, id=sheet_id, is_approved=True)
    current_question = get_object_or_404(Question, id=question_id)

    if current_question not in sheet.questions.all():
        messages.error(request, "This question is not a part of the sheet.")
        return redirect('my_sheet', slug=sheet.slug)

    # Get the next question in the sheet
    next_question = sheet.get_next_question(current_question)

    if next_question:
        # Render the next question
        return redirect('problem', slug=next_question.slug)

    else:
        messages.success(request, "You have completed all questions in this sheet.")
        return redirect('my_sheet', slug=sheet.slug)


# =================================================
def convert_backticks_to_code(text):
    pattern = r"`(.*?)`"
    result = re.sub(pattern, r"<code style='font-size: 110%'>\1</code>", text)
    return result

