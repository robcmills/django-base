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

    # update settings.py
    # change ALLOWED_HOSTS[0] to your ec2 instance public DNS
    # example:
    ALLOWED_HOSTS=['ec2-XX-XXX-XXX-XX.us-west-2.compute.amazonaws.com']

    # scp django_base_secret_key.txt to your ec2 instance

    # to enable fabfile create a local_settings.py from template
    # update FABRIC settings


### Deploy to EC2:

    fab all