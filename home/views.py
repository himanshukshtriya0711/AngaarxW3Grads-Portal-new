from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages as message
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Article, Comment, FlamesCourse, FlamesCourseTestimonial, FlamesRegistration
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count
from practice.models import Batch, Submission, Question
from django.contrib import messages
import requests
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


from administration.models import Achievement


def home(request):
    return render(request, "home/index.html")

def about(request):
    return render(request, "home/about.html")

def our_team(request):
    return render(request, "home/team.html")

def privacy_policy(request):
    return render(request, "home/privacy_policy.html")

def terms_of_service(request):
    return render(request, "home/terms_of_service.html")

# ======================== ARTICLES ========================

def articles(request):
    
    articles = Article.objects.all().order_by("-created_at")
    
    parameters = {
        "articles": articles,
        "user": request.user
    }
    
    return render(request, "home/articles.html", parameters)

# ==================== ARTICLE ============================

def article(request, slug):
    article = Article.objects.get(slug=slug)
    comments = Comment.objects.filter(article=article)
    
    # Show only preview (first 5 lines) if user is not logged in
    if not request.user.is_authenticated:
        content_lines = article.content.split("\n")[:25]  # Get first 5 lines
        preview_content = "\n".join(content_lines) + "<p>...</p>"
    else:
        preview_content = article.content  # Show full content if logged in

    return render(request, "home/article.html", {
        "article": article,
        "preview_content": preview_content,
        "comments": comments,
        "user": request.user
    })

# ==================== LIKE ARTICLE ============================

@login_required
def like_article(request):
    if request.method == 'POST':
        article_id = request.POST.get('article_id')
        article = get_object_or_404(Article, id=article_id)
        
        if request.user in article.likes.all():
            article.likes.remove(request.user)
            liked = False
        else:
            article.likes.add(request.user)
            liked = True
            
        return JsonResponse({
            'liked': liked,
            'total_likes': article.total_likes()
        })

# ==================== POST COMMENT ============================

@login_required
def post_comment(request, article_id):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        article = get_object_or_404(Article, id=article_id)
        content = request.POST.get('content')
        
        if content:
            comment = Comment.objects.create(
                article=article,
                user=request.user,
                content=content
            )
            
            return JsonResponse({
                'status': 'success',
                'comment': {
                    'author': comment.user.username,
                    'content': comment.content,
                    'created_at': comment.created_at.strftime("%B %d, %Y"),
                    'author_initial': comment.user.username[0],
                },
                'total_comments': article.comments.count()
            })
            
    return JsonResponse({'status': 'error'}, status=400)

# =======================================================================================
# ==================================== ACHIEVERS ========================================
# =======================================================================================


def our_achievers(request):
    return render(request, 'home/achievers.html')

def fetch_achievers_data(request):
    achievers = Achievement.objects.all().order_by('-date')[:4]
    data = []
    for achiever in achievers:
        data.append({
            'name': achiever.student.first_name + ' ' + achiever.student.last_name,
            'profile_pic': achiever.student.profile_pic.url,
            "linkedin": achiever.student.linkedin_id,
            "github": achiever.student.github_id,
            'title': achiever.title,
            'description': achiever.description,
            "achievement_type": achiever.achievement_type,
            'date': achiever.date.strftime('%Y-%m-%d'),
        })
    return JsonResponse(data, safe=False)

def fetch_top_performers(request):
    """
    Fetch the top performers for each batch based on the number of questions solved in the past week.
    """
    # Get the batch ID from the request, if provided
    batch_id = request.GET.get('batch_id')
    
    # Calculate the date range for the past week
    end_date = now()
    start_date = end_date - timedelta(days=7)
    
    # Base query to get submissions from the past week with 'Accepted' status
    base_query = Submission.objects.filter(
        submitted_at__gte=start_date,
        submitted_at__lte=end_date,
        status='Accepted'
    )
    
    # Initialize the data structure for the response
    data = {
        'batches': [],
        'top_performers': []
    }
    
    # If a specific batch is requested, filter by that batch
    if batch_id:
        batches = Batch.objects.filter(id=batch_id)
    else:
        # Otherwise, get all batches
        batches = Batch.objects.all()
    
    # For each batch, get the top performers
    for batch in batches:
        # Add batch info to the response
        data['batches'].append({
            'id': batch.id,
            'name': batch.name,
            'description': batch.description,
            'thumbnail': batch.thumbnail.url if batch.thumbnail else None,
        })
        
        # Get students enrolled in this batch
        enrolled_students = batch.students.filter(enrollment_requests__status='Accepted')
        
        # Get the count of accepted submissions for each student in this batch
        student_submissions = base_query.filter(
            user__in=enrolled_students,
            question__sheets__batches=batch
        ).values('user').annotate(
            solved_count=Count('question', distinct=True)
        ).order_by('-solved_count')[:5]  # Get top 5 performers
        
        # Add top performers for this batch to the response
        for submission in student_submissions:
            if submission['solved_count'] > 0:  # Only include students who solved at least one question
                student = enrolled_students.get(id=submission['user'])
                data['top_performers'].append({
                    'batch_id': batch.id,
                    'student_id': student.id,
                    'name': f"{student.first_name} {student.last_name}",
                    'profile_pic': student.profile_pic.url if student.profile_pic else None,
                    'linkedin': student.linkedin_id,
                    'github': student.github_id,
                    'solved_count': submission['solved_count'],
                    'batch_name': batch.name,
                })
    
    return JsonResponse(data, safe=False)

# ======================================= CERTIFICATE ================================

from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.conf import settings
from django.template.loader import render_to_string
from io import BytesIO
from django.core.cache import cache
from django.views.decorators.http import require_http_methods
from xhtml2pdf import pisa
from django_ratelimit.decorators import ratelimit
from student.event_models import Certificate

def get_client_ip(request):
    """Get the client's IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def check_rate_limit(request):
    """Check if the user has exceeded rate limits"""
    ip_address = get_client_ip(request)
    cache_key = f"cert_verify_rate_limit_{ip_address}"
    
    # Get current count
    current_count = cache.get(cache_key, 0)
    
    # Rate limit: 10 requests per hour per IP
    if current_count >= 10:
        return False
    
    # Increment counter
    cache.set(cache_key, current_count + 1, 60)  # 1 hour timeout
    return True

@require_http_methods(["GET", "POST"])
def verify_certificate(request):
    certificate_obj = None
    status = None

    if request.method == "POST":

        if not check_rate_limit(request):
            messages.warning(request, f"Too many requests from your end. Try again later.")
            return redirect('verify_certificate')

        cert_id = request.POST.get("certificate_id", "").strip().upper()
        if cert_id:
            try:
                certificate_obj = Certificate.objects.select_related("event", "student").get(certificate_id=cert_id)
                if certificate_obj.approved:
                    status = "approved"
                else:
                    status = "pending"
            except Certificate.DoesNotExist:
                status = "not_found"

        return render(request, "home/verify_my_certificate.html", {
            "certificate_obj": certificate_obj,
            "status": status
        })
    
    return render(request, "home/verify_my_certificate.html")


from django.template import Context, Template

# HTML(string=html_string).write_pdf(response)

from django.template import Context, Template
from django.http import HttpResponse, Http404
from io import BytesIO

def download_certificate(request, cert_id):
    try:
        certificate_obj = Certificate.objects.select_related(
            "event", "student", "template_version"
        ).get(certificate_id=cert_id, approved=True)
    except Certificate.DoesNotExist:
        raise Http404("Certificate not found or not approved.")

    template_obj = Template(certificate_obj.template_version.html_template)
    html_content = template_obj.render(Context({
        "student": certificate_obj.student,
        "event": certificate_obj.event,
        "issued_date": certificate_obj.issued_date.strftime("%B %d, %Y"),
        "certificate_id": certificate_obj.certificate_id,
    }))

    base_url = settings.STATIC_ROOT  # or your static folder path

    pdf_bytes = HTML(string=html_content, base_url=base_url).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{certificate_obj.certificate_id}.pdf"'
    return response


def link_callback(uri, rel):
    """Ensures static/media file paths work in xhtml2pdf."""
    import os
    from django.contrib.staticfiles import finders
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    elif uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, ""))
    else:
        return uri
    if not os.path.isfile(path):
        raise Exception(f"Media URI must start with {settings.STATIC_URL} or {settings.MEDIA_URL}")
    return path


# ======================================= CODE EXECUTION ================================

@csrf_exempt
@require_http_methods(["POST"])
def execute_code(request):
    """
    Execute code using Judge0 API
    """
    try:
        import json
        data = json.loads(request.body)
        source_code = data.get('source_code', '')
        
        if not source_code:
            return JsonResponse({
                'error': 'No source code provided'
            }, status=400)
        
        # Judge0 API configuration
        JUDGE0_API_KEY = '50e72a59c4msha2a0de8110e0aa9p1032ccjsn5de89ef15362'
        JUDGE0_HOST = 'judge0-ce.p.rapidapi.com'
        
        # Step 1: Create submission
        submission_url = f'https://{JUDGE0_HOST}/submissions?base64_encoded=false&wait=false'
        headers = {
            'content-type': 'application/json',
            'x-rapidapi-key': JUDGE0_API_KEY,
            'x-rapidapi-host': JUDGE0_HOST
        }
        
        submission_data = {
            'source_code': source_code,
            'language_id': 71,  # Python 3
            'stdin': ''
        }
        
        response = requests.post(submission_url, json=submission_data, headers=headers)
        
        if response.status_code != 201:
            return JsonResponse({
                'error': 'Failed to create submission',
                'details': response.text
            }, status=500)
        
        submission_result = response.json()
        token = submission_result.get('token')
        
        if not token:
            return JsonResponse({
                'error': 'No token received from Judge0'
            }, status=500)
        
        # Step 2: Poll for result
        result_url = f'https://{JUDGE0_HOST}/submissions/{token}?base64_encoded=false'
        max_attempts = 10
        attempt = 0
        
        while attempt < max_attempts:
            time.sleep(1)  # Wait 1 second between polls
            
            result_response = requests.get(result_url, headers=headers)
            
            if result_response.status_code != 200:
                return JsonResponse({
                    'error': 'Failed to get submission result',
                    'details': result_response.text
                }, status=500)
            
            result = result_response.json()
            status_id = result.get('status', {}).get('id', 0)
            
            # Status IDs: 1 = In Queue, 2 = Processing, 3+ = Done
            if status_id > 2:
                # Execution completed
                return JsonResponse({
                    'status': 'success',
                    'result': {
                        'status': result.get('status', {}),
                        'stdout': result.get('stdout', ''),
                        'stderr': result.get('stderr', ''),
                        'compile_output': result.get('compile_output', ''),
                        'time': result.get('time', ''),
                        'memory': result.get('memory', '')
                    }
                })
            
            attempt += 1
        
        # Timeout
        return JsonResponse({
            'error': 'Execution timeout - please try again'
        }, status=408)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)
