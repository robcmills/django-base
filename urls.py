from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # url(r'^$', 'django_base.views.home', name='home'),
    url(r'^$', include('base_app.urls', namespace='base')),
    url(r'^admin/', include(admin.site.urls)),
)
