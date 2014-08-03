
import settings


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# DEPLOY SETTINGS
FABRIC = {
    "SSH_USER": "ubuntu", # SSH username for host deploying to
    "SSH_PASS": "ubuntu", # SSH password for user ubuntu
    "SSH_KEY_PATH": "~/path/to/key-pair.pem",
    "HOSTS": settings.ALLOWED_HOSTS[:1], # List of hosts to deploy to (eg, first host)
    "DOMAINS": settings.ALLOWED_HOSTS, # Domains for public site
    "REPO_URL": "https://github.com/robcmills/django-base.git", # Project's repo URL
    # "VIRTUALENV_HOME":  "/home/ubuntu", # Absolute remote path for virtualenvs
    "PROJECT_NAME": "django_base", # Unique identifier for project
    "REQUIREMENTS_PATH": "requirements.txt", # Project's pip requirements
    "GUNICORN_PORT": 8000, # Port gunicorn will listen on
    "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
    "DB_PASS": "password", # Live database password
    "ADMIN_PASS": "admin", # Live admin user password
    "SECRET_KEY": settings.SECRET_KEY,
    # "NEVERCACHE_KEY": os.environ.get('NEVERCACHE_KEY'),
}

# useful commands 

# ssh into an ec2 instance:
# ssh -l [username] -i [~/path/to/key-pair.pem] [ip_address]

# secure copy files to ec2 instance
# scp -i ~/.ec2/key-pair.pem /path/to/local/file.txt username@EC2-HOST.compute.amazonaws.com:/path/to/remote/dir
