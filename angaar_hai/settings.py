from pathlib import Path
from django.contrib.messages import constants as messages
from dotenv import load_dotenv

import os

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True") == "True"


ALLOWED_HOSTS = ["*"]

INTERNAL_IPS = ['127.0.0.1', "localhost"]
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = ["https://4b228b8116a58fd4ec1be36bb4a449ec.serveo.net"]

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    'accounts.apps.AccountsConfig',
    'home.apps.HomeConfig',
    'student.apps.StudentConfig',
    'administration.apps.AdministrationConfig',
    'practice.apps.PracticeConfig',
    'instructor.apps.InstructorConfig',
    
    # 'single_session',
    'import_export',
    'corsheaders',
    'dbbackup',
    'django_ratelimit',
    'debug_toolbar',
    'django_celery_beat',
    
    "channels",

    'allauth',
    'allauth.account', 
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',


]

MIDDLEWARE = [
    
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    'corsheaders.middleware.CorsMiddleware',
    
    'debug_toolbar.middleware.DebugToolbarMiddleware',

    'allauth.account.middleware.AccountMiddleware',
    'angaar_hai.middleware.MaintenanceModeMiddleware',

    
]

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

ROOT_URLCONF = 'angaar_hai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ["templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'student.context_processors.user_context_processor',
                'student.context_processors.streak_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'angaar_hai.wsgi.application'

# ASGI application
ASGI_APPLICATION = 'angaar_hai.asgi.application'

# Use Redis for Channels layer (Highly Recommended for Production)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': "angaar",
        'USER': "root",
        'PASSWORD': "himanshu",
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}




# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    # {
    #     'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    # },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    # },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    # },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    # },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/


STATIC_URL = '/static/'

# Add Manually

STATICFILES_DIRS = [
    BASE_DIR / "demo_static",
]

STATIC_ROOT = BASE_DIR / "static"


MEDIA_URL = '/media/'
MEDIA_ROOT  = BASE_DIR / 'media'

CKEDITOR_UPLOAD_PATH = "uploads/"


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



MESSAGE_TAGS = {
    messages.DEBUG: 'alert-secondary',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}


CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

X_FRAME_OPTIONS = 'SAMEORIGIN'

SINGLE_USER_SESSION = True

DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': 'backups'}


SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE")
SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY")
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE")

# settings.py



# ===================================================================================================


# ==================================================================================================

# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'formatters': {
#         'verbose': {
#             'format': 'Level: {levelname} | Time: {asctime} | Module: {module} | Message: {message}',
#             'style': '{',
#         },
#         'simple': {
#             'format': '{levelname} | {message}',
#             'style': '{',
#         },
#     },
#     'handlers': {
#         'file': {
#             'level': 'WARNING',
#             'class': 'logging.FileHandler',
#             'filename': 'errors.log',
#             'formatter': 'verbose',
#         },
#     },
#     'loggers': {
#         'django': {
#             'handlers': ['file'],
#             'level': 'DEBUG',
#             'propagate': True,
#         },
#         'myapp': {
#             'handlers': ['file'],
#             'level': 'INFO',
#             'propagate': False,
#         },
#     },
# }

# Email Backend for Brevo
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp-relay.brevo.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "82930f002@smtp-brevo.com"
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = 'noreply@theangaarbatch.in'


CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',  # Use your Redis server address
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

# Celery Configuration
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/2'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/2'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kolkata'


# MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# Add to settings.py
# RAZORPAY_KEY_ID = 'rzp_test_3SQlSCQ0alBcCn'
# RAZORPAY_KEY_SECRET = 'rQDEoRRaZ3DnAuQjWMuuelIa'

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


JUDGE0_CALLBACK_URL = "https://1b49f750e5d68e7a9c33c24612db101e.serveo.net/judge0/callback"

# =================== AllAuth Settings =========================


SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Custom adapters
ACCOUNT_ADAPTER = 'accounts.adapters.CustomAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.CustomSocialAccountAdapter'

# Login/Logout URLs
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# Account settings
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Google handles email verification
ACCOUNT_USERNAME_REQUIRED = False    # We generate usernames automatically
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
ACCOUNT_USER_MODEL_EMAIL_FIELD = 'email'

# Social account settings - FIXED FOR SMOOTH OAUTH
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_LOGIN_ON_GET = True   # CHANGED: This eliminates the intermediate page
SOCIALACCOUNT_STORE_TOKENS = False

# Google OAuth Provider Configuration - REMOVE APP SECTION
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,  # Better security
        'FETCH_USERINFO': True,      # Get user info
        # REMOVED APP SECTION - Using database SocialApp instead
    }
}

CSRF_COOKIE_HTTPONLY = True

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")