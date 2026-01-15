from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from home.models import FlamesCourse, FlamesRegistration, FlamesTeam, FlamesTeamMember, Session
from .event_models import Event, CertificateTemplate, Certificate
from django.template.loader import get_template
from django.template import engines, Template, Context
# from weasyprint import HTML
from django.http import HttpResponse

# ======================================= FLAMES MAIN PAGE ================================

@login_required(login_url='login')
def student_flames(request):
    # Get registrations where the user is directly registered
    direct_registrations = FlamesRegistration.objects.filter(
        user=request.user
    ).select_related('course', 'team').order_by('-created_at')
    
    # Find teams where the user is a member but not the team leader
    team_memberships = FlamesTeamMember.objects.filter(
        member=request.user,
        is_leader=False
    ).select_related('team')
    
    team_ids = team_memberships.values_list('team_id', flat=True)
    
    # Get registrations for teams where the user is a member
    team_registrations = FlamesRegistration.objects.filter(
        team_id__in=team_ids
    ).select_related('course', 'team').order_by('-created_at')
    
    # Combine both types of registrations
    registrations = list(direct_registrations)
    
    # Add team registrations if they're not already included
    for reg in team_registrations:
        if reg not in registrations:
            registrations.append(reg)
    
    # Sort by created_at (most recent first)
    registrations.sort(key=lambda x: x.created_at, reverse=True)
    
    # Prefetch team members for all registrations with teams
    for registration in registrations:
        if registration.team:
            registration.team.members_list = FlamesTeamMember.objects.filter(team=registration.team)
    
    # Get available courses (courses that the student hasn't registered for)
    registered_course_ids = set()
    for reg in registrations:
        registered_course_ids.add(reg.course_id)
    
    available_courses = FlamesCourse.objects.filter(is_active=True).exclude(id__in=registered_course_ids)

    
    parameters = {
        'registrations': registrations,
        'available_courses': available_courses,
        'active_tab': 'flames',
    }
    
    return render(request, 'student/flames/flames.html', parameters)


# ====================================== VIEW REGISTRATION ================================

@login_required(login_url='login')
def view_registration(request, slug):
    course = get_object_or_404(FlamesCourse, slug=slug)
    
    # Get the registration with related course data
    registration = FlamesRegistration.objects.filter(
        user=request.user,
        course=course
    ).select_related('course', 'team', 'referral_code').first()
    
    # If not found, check if the user is a team member
    if not registration:
        # Check if user is part of a team registered for this course
        from home.models import FlamesTeamMember
        team_memberships = FlamesTeamMember.objects.filter(
            member=request.user,
            team__registrations__course=course
        ).select_related('team')
        
        if team_memberships.exists():
            # Get the registration through the team
            team = team_memberships.first().team
            registration = FlamesRegistration.objects.filter(
                team=team,
                course=course
            ).select_related('course', 'team', 'referral_code').first()
        else:
            messages.error(request, "You are not registered for this course.")
            return redirect('student_flames')
    
    # If this is a team registration, prefetch team members
    if registration.registration_mode == 'TEAM' and registration.team:
        from django.db.models import Prefetch
        from home.models import FlamesTeamMember
        
        # Prefetch team members with their student information
        team_members = FlamesTeamMember.objects.filter(
            team=registration.team
        ).select_related('member')
        
        # Attach the members to the team object
        registration.team.members_list = team_members
    
    parameters = {
        'registration': registration,
        'course': course,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    }
    
    return render(request, 'student/flames/view_registration.html', parameters)


# ========================================= MY COURSE =====================================

@login_required(login_url='login')
def my_course(request, slug):

    course = get_object_or_404(FlamesCourse, slug=slug)

    registration = FlamesRegistration.objects.filter(
        user=request.user,
        course=course,
        status__in=['Approved', "Completed"]
    ).select_related('course', 'team').first()

    if not registration:
        messages.error(request, "You are not registered for this course.")
        return redirect('student_flames')
    
    if course.id == 8: # means bundle offer combining course having id 3 and 4
        dsa_sessions = Session.objects.filter(
            course__id=3
        ).order_by('start_datetime')

        full_stack_sessions = Session.objects.filter(
            course__id=4
        ).order_by('start_datetime')

        parameters = {
            'registration': registration,
            'course': course,
            'dsa_sessions': dsa_sessions,
            'full_stack_sessions': full_stack_sessions,
        }
    
    else:
        sessions = Session.objects.filter(
            course=course
        ).order_by('start_datetime')

        parameters = {
            'registration': registration,
            'course': course,
            'sessions': sessions,
        }

    return render(request, 'student/flames/my_course.html', parameters)


# ========================================= VIEW CERTIFICATE =====================================

# @login_required(login_url='login')
# def view_certificate(request, id):
    # certificate = get_object_or_404(Certificate, id=id, student=request.user)
    
    # # Check if the certificate is associated with an event
    # if not certificate.event:
    #     messages.error(request, "This certificate is not valid or does not exist.")
    #     return redirect('student_flames')
    
    # # Render the certificate template
    # template = get_template('student/flames/certificate_template.html')
    # context = {
    #     'certificate': certificate,
    #     'event': certificate.event,
    #     'student': request.user,
    # }
    
    # html_content = template.render(context)
    
    # # Generate PDF from HTML content
    # pdf_file = HTML(string=html_content).write_pdf()
    
    # response = HttpResponse(pdf_file, content_type='application/pdf')
    # response['Content-Disposition'] = f'attachment; filename="{certificate.certificate_id}.pdf"'
    
    # return response


























































# @login_required
# def team_formation(request):
#     """
#     Manage team formation for solo registrations
#     """
#     # Get student's solo registrations that don't have a team yet
#     solo_registrations = FlamesRegistration.objects.filter(
#         user=request.user,
#         registration_mode='SOLO',
#         team__isnull=True
#     ).select_related('course')
    
#     # Get student's teams
#     teams = FlamesTeam.objects.filter(
#         team_leader=request.user
#     ).prefetch_related('members')
    
#     context = {
#         'solo_registrations': solo_registrations,
#         'teams': teams,
#         'active_tab': 'flames_teams'
#     }
    
#     return render(request, 'student/flames/team_formation.html', context)

# @login_required
# def create_team(request, registration_id):
#     """
#     Create a team for a solo registration
#     """
#     registration = get_object_or_404(
#         FlamesRegistration, 
#         id=registration_id, 
#         user=request.user, 
#         registration_mode='SOLO',
#         team__isnull=True
#     )
    
#     if request.method == 'POST':
#         team_name = request.POST.get('team_name')
        
#         if not team_name:
#             messages.error(request, "Team name is required.")
#             return redirect('student_team_formation')
        
#         # Create the team
#         team = FlamesTeam.objects.create(
#             name=team_name,
#             team_leader=request.user,
#             course=registration.course
#         )
        
#         # Link the registration to the team
#         registration.team = team
#         registration.save()
        
#         # Add the user as the first team member
#         FlamesTeamMember.objects.create(
#             team=team,
#             full_name=registration.full_name,
#             email=registration.email,
#             contact_number=registration.contact_number,
#             user=request.user,
#             is_leader=True
#         )
        
#         messages.success(request, f"Team '{team_name}' created successfully!")
#         return redirect('student_team_formation')
    
#     # GET request
#     return render(request, 'student/flames/create_team.html', {
#         'registration': registration,
#         'active_tab': 'flames_teams'
#     })

# @login_required
# def add_team_member(request, team_id):
#     """
#     Add a team member to an existing team
#     """
#     team = get_object_or_404(FlamesTeam, id=team_id, team_leader=request.user)
    
#     # Check if team is already full
#     if team.members.count() >= 5:
#         messages.error(request, "This team already has the maximum number of members (5).")
#         return redirect('student_team_formation')
    
#     if request.method == 'POST':
#         full_name = request.POST.get('full_name')
#         email = request.POST.get('email')
#         contact_number = request.POST.get('contact_number')
        
#         if not all([full_name, email, contact_number]):
#             messages.error(request, "All fields are required.")
#             return redirect('student_add_team_member', team_id=team.id)
        
#         # Check if email is already in the team
#         if team.members.filter(email=email).exists():
#             messages.error(request, f"A member with email '{email}' is already in this team.")
#             return redirect('student_add_team_member', team_id=team.id)
        
#         # Add new team member
#         FlamesTeamMember.objects.create(
#             team=team,
#             full_name=full_name,
#             email=email,
#             contact_number=contact_number
#         )
        
#         messages.success(request, f"{full_name} has been added to the team.")
#         return redirect('student_team_formation')
    
#     # GET request
#     return render(request, 'student/flames/add_team_member.html', {
#         'team': team,
#         'active_tab': 'flames_teams'
#     })

# @login_required
# def remove_team_member(request, member_id):
#     """
#     Remove a team member from a team
#     """
#     # Only allow removal if the user is the team leader and the member is not the leader
#     member = get_object_or_404(
#         FlamesTeamMember, 
#         id=member_id, 
#         team__team_leader=request.user,
#         is_leader=False
#     )
    
#     team = member.team
#     member_name = member.full_name
    
#     # Delete the member
#     member.delete()
    
#     messages.success(request, f"{member_name} has been removed from the team.")
#     return redirect('student_team_formation')
