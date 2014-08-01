from __future__ import print_function, unicode_literals
from future.builtins import input, open

import os
import re
import sys
from functools import wraps
from getpass import getpass, getuser
# from glob import glob
from contextlib import contextmanager
from posixpath import join

from fabric.api import env, cd, prefix, sudo as _sudo, run as _run, hide, task
from fabric.contrib.files import exists, upload_template
from fabric.colors import yellow, green, blue, red


################
# Config setup #
################

conf = {}
if sys.argv[0].split(os.sep)[-1] in ("fab", "fab-script.py"):
    # Ensure we import settings from the current dir
    try:
        conf = __import__("settings", globals(), locals(), [], 0).FABRIC
        try:
            conf["HOSTS"][0]
        except (KeyError, ValueError):
            raise ImportError
    except (ImportError, AttributeError):
        print("Aborting, no hosts defined.")
        exit()

env.db_pass = conf.get("DB_PASS", None)
env.admin_pass = conf.get("ADMIN_PASS", None)
env.user = conf.get("SSH_USER", getuser())
env.password = conf.get("SSH_PASS", None)
env.key_filename = conf.get("SSH_KEY_PATH", None)
env.hosts = conf.get("HOSTS", [""])

env.proj_name = conf.get("PROJECT_NAME", os.getcwd().split(os.sep)[-1])
env.venv_home = conf.get("VIRTUALENV_HOME", "/home/%s" % env.user) # /home/ubuntu
env.venv_path = "%s/%s" % (env.venv_home, env.proj_name) # /home/ubuntu/mezzanine_base
env.proj_dirname = "project"
env.proj_path = "%s/%s" % (env.venv_path, env.proj_dirname) # /home/ubuntu/mezzanine_base/project
env.manage = "%s/env/bin/python %s/project/manage.py" % ((env.venv_path,) * 2)
env.domains = conf.get("DOMAINS", [conf.get("LIVE_HOSTNAME", env.hosts[0])])
env.domains_nginx = " ".join(env.domains)
env.domains_python = ", ".join(["'%s'" % s for s in env.domains])
env.ssl_disabled = "# "
env.repo_url = conf.get("REPO_URL", "")
env.git = env.repo_url.startswith("git") or env.repo_url.endswith(".git")
env.reqs_path = conf.get("REQUIREMENTS_PATH", None)
env.gunicorn_port = conf.get("GUNICORN_PORT", 8000)
env.locale = conf.get("LOCALE", "en_US.UTF-8")

env.secret_key = conf.get("SECRET_KEY", "")
# env.nevercache_key = conf.get("NEVERCACHE_KEY", "")


##################
# Template setup #
##################

# Each template gets uploaded at deploy time, only if their
# contents have changed, in which case, the reload command is
# also run.

templates = {
    "nginx_ec2": {
        "local_path": "deploy/nginx.ec2.conf",
        "remote_path": "/etc/nginx/nginx.conf",
        "reload_command": "nginx -s reload",
    },
    "nginx_site": {
        "local_path": "deploy/nginx.conf",
        "remote_path": "/etc/nginx/sites-enabled/%(proj_name)s.conf",
        "reload_command": "nginx -s reload",
    },
    "supervisor": {
        "local_path": "deploy/supervisor.conf",
        "remote_path": "/etc/supervisor/conf.d/%(proj_name)s.conf",
        "reload_command": "supervisorctl reload",
    },
    "cron": {
        "local_path": "deploy/crontab",
        "remote_path": "/etc/cron.d/%(proj_name)s",
        "owner": "root",
        "mode": "600",
    },
    "gunicorn": {
        "local_path": "deploy/gunicorn.conf.py.template",
        "remote_path": "%(proj_path)s/gunicorn.conf.py",
    },
    "settings": {
        "local_path": "deploy/local_settings.py.template",
        "remote_path": "%(proj_path)s/local_settings.py",
    },
}


######################################
# Context for virtualenv and project #
######################################

@contextmanager
def virtualenv():
    """
    Runs commands within the project's virtualenv.
    """
    with cd(env.venv_path):
        with prefix("source %s/env/bin/activate" % env.venv_path):
            yield


@contextmanager
def project():
    """
    Runs commands within the project's directory.
    """
    print_command('project: ' + env.proj_dirname)
    with virtualenv():
        with cd(env.proj_dirname):
            yield


@contextmanager
def update_changed_requirements():
    """
    Checks for changes in the requirements file across an update,
    and gets new requirements if changes have occurred.
    """
    print_command("update_changed_requirements")
    reqs_path = join(env.proj_path, env.reqs_path)
    get_reqs = lambda: run("cat %s" % reqs_path, show=False)
    old_reqs = get_reqs() if env.reqs_path else ""
    yield
    if old_reqs:
        new_reqs = get_reqs()
        if old_reqs == new_reqs:
            # Unpinned requirements should always be checked.
            for req in new_reqs.split("\n"):
                if req.startswith("-e"):
                    if "@" not in req:
                        # Editable requirement without pinned commit.
                        break
                elif req.strip() and not req.startswith("#"):
                    if not set(">=<") & set(req):
                        # PyPI requirement without version.
                        break
            else:
                # All requirements are pinned.
                return
        pip("-r %s/%s" % (env.proj_path, env.reqs_path))


###########################################
# Utils and wrappers for various commands #
###########################################

def _print(output):
    print()
    print(output)
    print()


def print_command(command):
    _print(blue("$ ", bold=True) +
           yellow(command, bold=True) +
           red(" ->", bold=True))


@task
def run(command, show=True):
    """
    Runs a shell comand on the remote server.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _run(command)


@task
def sudo(command, show=True):
    """
    Runs a command as sudo.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _sudo(command)


def log_call(func):
    @wraps(func)
    def logged(*args, **kawrgs):
        header = "-" * len(func.__name__)
        _print(green("\n".join([header, func.__name__, header]), bold=True))
        return func(*args, **kawrgs)
    return logged


def get_templates():
    """
    Returns each of the templates with env vars injected.
    """
    injected = {}
    for name, data in templates.items():
        injected[name] = dict([(k, v % env) for k, v in data.items()])
    return injected


def upload_template_and_reload(name):
    """
    Uploads a template only if it has changed, and if so, reload a
    related service.
    """
    print_command('upload_template_and_reload: ' + name)
    template = get_templates()[name]
    local_path = template["local_path"] # deploy/local_settings.py.template
    if not os.path.exists(local_path):
        project_root = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(project_root, local_path)
    remote_path = template["remote_path"] # %(proj_path)s/local_settings.py
    reload_command = template.get("reload_command")
    owner = template.get("owner")
    mode = template.get("mode")
    remote_data = ""
    if exists(remote_path):
        with hide("stdout"):
            remote_data = sudo("cat %s" % remote_path, show=False)
    with open(local_path, "r") as f:
        local_data = f.read()
        # Escape all non-string-formatting-placeholder occurrences of '%':
        local_data = re.sub(r"%(?!\(\w+\)s)", "%%", local_data)
        if "%(db_pass)s" in local_data:
            env.db_pass = db_pass()
        local_data %= env
    clean = lambda s: s.replace("\n", "").replace("\r", "").strip()
    if clean(remote_data) == clean(local_data):
        return
    upload_template(local_path, remote_path, env, use_sudo=True, backup=False)
    if owner:
        sudo("chown %s %s" % (owner, remote_path))
    if mode:
        sudo("chmod %s %s" % (mode, remote_path))
    if reload_command:
        sudo(reload_command)


@task
def upload_template_and_restart(name):
    """
    Uploads a template only if it has changed, and if so, reload a
    related service and then restart 
    """
    upload_template_and_reload(name)
    restart()


def db_pass():
    """
    Prompts for the database password if unknown.
    """
    if not env.db_pass:
        env.db_pass = getpass("Enter the database password: ")
    return env.db_pass


@task
def apt(packages):
    """
    Installs one or more system packages via apt.
    """
    return sudo("apt-get install -y -q " + packages)


@task
def pip(packages):
    """
    Installs one or more Python packages within the virtual environment.
    """
    with virtualenv():
        return sudo("pip install %s" % packages)


def postgres(command):
    """
    Runs the given command as the postgres user.
    """
    show = not command.startswith("psql")
    return run("sudo -u root sudo -u postgres %s" % command, show=show)


@task
def psql(sql, show=True):
    """
    Runs SQL against the project's database.
    """
    out = postgres('psql -c "%s"' % sql)
    if show:
        print_command(sql)
    return out


@task
def backup(filename):
    """
    Backs up the database.
    """
    return postgres("pg_dump -Fc %s > %s" % (env.proj_name, filename))


@task
def restore(filename):
    """
    Restores the database.
    """
    return postgres("pg_restore -c -d %s %s" % (env.proj_name, filename))


@task
def python(code, show=True):
    """
    Runs Python code in the project's virtual environment, with Django loaded.
    """
    setup = "import os; os.environ[\'DJANGO_SETTINGS_MODULE\']=\'settings\';"
    full_code = 'python -c "%s%s"' % (setup, code.replace("`", "\\\`"))
    with project():
        result = run(full_code, show=False)
        if show:
            print_command(code)
    return result


def static():
    """
    Returns the live STATIC_ROOT directory.
    """
    return python("from django.conf import settings;"
                  "print settings.STATIC_ROOT", show=False).split("\n")[-1]


@task
def manage(command):
    """
    Runs a Django management command.
    """
    return run("%s %s" % (env.manage, command))


#########################
# Install and configure #
#########################

@task
@log_call
def update():
    sudo("apt-get update -y -q")


@task
@log_call
def install():
    apt("nginx libjpeg-dev python-dev python-setuptools git-core "
        "sqlite3 libpq-dev memcached supervisor")
    sudo("easy_install pip")
    sudo("pip install virtualenv")


@task
@log_call
def create():
    """
    Create a new virtual environment for a project,
    Pull the project's repo from version control, 
    install requirements,
    add system-level configs for the project.
    """

    # Create virtualenv & clone repo
    if not exists(env.venv_path): # /home/ubuntu/mezzanine_base
        run("mkdir %s" % env.venv_path)
    with cd(env.venv_path):
        if not exists('env'):
            run("virtualenv env")
        if not exists('project'):
            run("git clone %s project" % (env.repo_url))

    # TODO: Create DB and DB user.
    # TODO: Set up SSL certificate.

    # Set up project.
    upload_template_and_reload("settings")
    with project(): # /home/ubuntu/mezzanine_base/project
        pip("-r %s/requirements.txt" % (env.proj_path))
        pip("setproctitle south psycopg2 "
            "django-compressor python-memcached")
        # manage("createdb --noinput --nodata")
        # TODO: update Site and User models
    return True


@task
@log_call
def remove():
    """
    Blow away the current project.
    """
    if exists(env.venv_path):
        sudo("rm -rf %s" % env.venv_path)
    for template in get_templates().values():
        remote_path = template["remote_path"]
        if exists(remote_path):
            sudo("rm %s" % remote_path)
    # psql("DROP DATABASE IF EXISTS %s;" % env.proj_name)
    # psql("DROP USER IF EXISTS %s;" % env.proj_name)


##############
# Deployment #
##############

@task
@log_call
def restart():
    """
    Restart gunicorn worker processes for the project.
    """
    pid_path = "%s/gunicorn.pid" % env.proj_path
    if exists(pid_path):
        sudo("kill -HUP `cat %s`" % pid_path)
    else:
        start_args = (env.proj_name, env.proj_name)
        sudo("supervisorctl start %s:gunicorn_%s" % start_args)


@task
@log_call
def deploy():
    """
    Deploy latest version of the project.
    pull latest from vcs,
    install new requirements, 
    # TODO: sync and migrate the database,
    collect any new static assets, and 
    restart gunicorn's work processes for the project.
    """
    # ensure global nginx conf loads first
    upload_template_and_reload('nginx_ec2')
    for name in get_templates():
        upload_template_and_reload(name)
    with project(): # /home/ubuntu/mezzanine_base/project
        static_dir = static()
        with update_changed_requirements():
            run("git pull origin master -f")
        manage("collectstatic -v 0 --noinput")
        # manage("syncdb --noinput")
        # manage("migrate --noinput")
    restart()
    return True


@task
@log_call
def rollback():
    """
    Reverts project state to the last deploy.
    When a deploy is performed, the current state of the project is
    backed up. This includes the last commit checked out, the database,
    and all static files. Calling rollback will revert all of these to
    their state prior to the last deploy.
    """
    with project():
        with update_changed_requirements():
            update = "git checkout" if env.git else "hg up -C"
            run("%s `cat last.commit`" % update)
        with cd(join(static(), "..")):
            run("tar -xf %s" % join(env.proj_path, "last.tar"))
        restore("last.db")
    restart()


@task
@log_call
def all():
    """
    Installs everything required on a new system and deploys.
    From the base software, up to the deployed project.
    """
    install()
    if create():
        deploy()
