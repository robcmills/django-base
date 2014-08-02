django-base
===========

minimal django app base template configured for fabric deployment to aws ec2


### Setup:

    mkdir django-base
    cd django-base

    virtualenv env
    . env/bin/activate

    git clone https://github.com/robcmills/django-base.git project
    cd project
    pip install -r requirements.txt

    # settings.py
    # change ALLOWED_HOSTS[0] to your ec2 instance public DNS
    # example:
    ALLOWED_HOSTS=['ec2-XX-XXX-XXX-XX.us-west-2.compute.amazonaws.com']

    # change TIME_ZONE

    # FABRIC settings:
    # change SSH_KEY_PATH to point to your key
    # example: 
    "SSH_KEY_PATH": "~/.ec2/my-key-pair.pem",


### Deploy to EC2:

    fab all