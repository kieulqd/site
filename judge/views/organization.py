from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView, RedirectView, View, UpdateView
from django.views.generic.detail import SingleObjectMixin

from judge.models import Organization
from judge.utils.ranker import ranker
from judge.utils.views import generic_message, TitleMixin, LoginRequiredMixin


__all__ = ['OrganizationList', 'OrganizationHome', 'OrganizationUsers', 'JoinOrganization',
           'LeaveOrganization', 'NewOrganization']


def organization_not_found(request, key):
    if key:
        return generic_message(request, 'No such organization',
                               'Could not find an organization with the key "%s".' % key)
    else:
        return generic_message(request, 'No such organization',
                               'Could not find such organization.')


class OrganizationList(TitleMixin, ListView):
    model = Organization
    context_object_name = 'organizations'
    template_name = 'organizations.jade'
    title = 'Organizations'


class OrganizationMixin(object):
    context_object_name = 'organization'
    model = Organization
    slug_field = 'key'
    slug_url_kwarg = 'key'

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(OrganizationMixin, self).dispatch(self, request, *args, **kwargs)
        except Http404:
            return organization_not_found(request, kwargs.get(self.slug_url_kwarg, None))


class OrganizationHome(TitleMixin, OrganizationMixin, DetailView):
    template_name = 'organization.jade'

    def get_title(self):
        return self.object.name


class OrganizationUsers(OrganizationMixin, DetailView):
    template_name = 'users.jade'

    def get_context_data(self, **kwargs):
        context = super(OrganizationUsers, self).get_context_data(**kwargs)
        context['title'] = '%s Members' % self.object.name
        context['users'] = ranker(self.object.members.filter(points__gt=0, user__is_active=True).order_by('-points'))
        return context


class OrganizationMembershipChange(LoginRequiredMixin, OrganizationMixin, SingleObjectMixin, View):
    def get(self, request, *args, **kwargs):
        try:
            org = self.get_object()
        except Http404:
            return organization_not_found(request, kwargs.get(self.slug_url_kwarg, None))
        response = self.handle(request, org, request.user.profile)
        if response is not None:
            return response
        return HttpResponseRedirect(reverse('organization_home', args=(org.key,)))

    def handle(self, request, org, profile):
        raise NotImplementedError()


class JoinOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if profile.organization_id is not None:
            return generic_message(request, 'Joining organization', 'You are already in an organization.')
        profile.organization = org
        profile.organization_join_time = timezone.now()
        profile.save()
        cache.delete(make_template_fragment_key('org_member_count', (org.id,)))


class LeaveOrganization(OrganizationMembershipChange):
    def handle(self, request, org, profile):
        if org.id != profile.organization_id:
            return generic_message(request, 'Leaving organization', 'You are not in "%s".' % org.key)
        profile.organization = None
        profile.organization_join_time = None
        profile.save()
        cache.delete(make_template_fragment_key('org_member_count', (org.id,)))


class NewOrganization(LoginRequiredMixin, CreateView):
    template_name = 'new_organization.jade'
    model = Organization
    fields = ['name', 'key', 'about']

    def form_valid(self, form):
        form.instance.registrant = self.request.user.profile
        return super(NewOrganization, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        profile = request.user.profile
        if profile.points < 50:
            return generic_message(request, "Can't add organization",
                                   'You need 50 points to add an organization.')
        elif profile.organization is not None:
            return generic_message(request, "Can't add organization",
                                   'You are already in an organization.')
        return super(NewOrganization, self).dispatch(request, *args, **kwargs)


class EditOrganization(LoginRequiredMixin, OrganizationMixin, UpdateView):
    fields = ['name', 'about']
    template_name = 'edit_organization.jade'

    def get_object(self, queryset=None):
        object = super(EditOrganization, self).get_object()
        if object.id != self.request.user.profile.organization_id:
            raise PermissionDenied()

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(EditOrganization, self).dispatch(request, *args, **kwargs)
        except PermissionDenied:
            return generic_message(request, "Can't edit organization",
                                   'You are not in this organization.')
