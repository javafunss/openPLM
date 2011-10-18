#-!- coding:utf-8 -!-

############################################################################
# openPLM - open source PLM
# Copyright 2010 Philippe Joulaud, Pierre Cosquer
# 
# This file is part of openPLM.
#
#    openPLM is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    openPLM is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
# Contact :
#    Philippe Joulaud : ninoo.fr@gmail.com
#    Pierre Cosquer : pierre.cosquer@insa-rennes.fr
################################################################################

"""
Introduction
=============

This module contains all views to display html pages.

All URLs are linked with django's standard views or with plmapp view functions hereafter.
Each of them receives an httprequest object.
Then treat data with the help of different controllers and different models.
Then adress a html template with a context dictionnary via an httpresponse.

We have a view for each :class:`PLMObject` or :class:`UserProfile` :func:`menu_items`.
We have some views which allow link creation between 2 instances of :class:`PLMObject` or between
an instance of :class:`PLMObject` and an instance of :class:`UserProfile`.
We have some views for link deletion.
We have some views for link edition.
We have views for :class:`PLMObject` creation and edition.
Finaly we have :func:`navigate` which draw a picture with a central object and its related objects.

"""

import os
import csv
import datetime
import tempfile
import itertools
from operator import attrgetter
from mimetypes import guess_type

from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect, HttpResponse,\
                        HttpResponsePermanentRedirect, HttpResponseForbidden
from django.template import RequestContext
from django.contrib.auth.forms import PasswordChangeForm
from django.utils.encoding import iri_to_uri
from django.utils.translation import ugettext_lazy as _
from django.forms import HiddenInput

from openPLM.plmapp.exceptions import ControllerError, PermissionError
import openPLM.plmapp.models as models
from openPLM.plmapp.controllers import get_controller 
from openPLM.plmapp.utils import level_to_sign_str, get_next_revision
from openPLM.plmapp.forms import *
import openPLM.plmapp.forms as forms
from openPLM.plmapp.base_views import get_obj, get_obj_from_form, \
    get_obj_by_id, handle_errors, get_generic_data, get_navigate_data
import openPLM.plmapp.csvimport as csvimport

def r2r(template, dictionary, request):
    """
    Shortcut for::
        
        render_to_response(template, dictionary,
                              context_instance=RequestContext(request))
    """
    return render_to_response(template, dictionary,
                              context_instance=RequestContext(request))

##########################################################################################
###                    Function which manage the html home page                        ###
##########################################################################################
@handle_errors
def display_home_page(request):
    """
    Once the user is logged in, redirection to his/her own user object with :func:navigate
    """
    return HttpResponseRedirect("/user/%s/navigate/" % request.user)

#############################################################################################
###All functions which manage the different html pages related to a part, a doc and a user###
#############################################################################################
@handle_errors
def display_object_attributes(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays attributes of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    object_attributes_list = []
    for attr in obj.attributes:
        item = obj.get_verbose_name(attr)
        object_attributes_list.append((item, getattr(obj, attr)))
    ctx.update({'current_page' : 'attributes',
                'object_attributes': object_attributes_list})
    return r2r('DisplayObject.htm', ctx, request)

##########################################################################################
@handle_errors
def display_object(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays attributes of the selected object.
    Redirection to :func:display_object_attributes
    """
     
    if obj_type in ('User', 'Group'):
        url = u"/%s/%s/attributes/" % (obj_type.lower(), obj_ref)
    else:
        url = u"/object/%s/%s/%s/attributes/" % (obj_type, obj_ref, obj_revi) 
    return HttpResponsePermanentRedirect(iri_to_uri(url))

##########################################################################################
@handle_errors
def display_object_lifecycle(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays lifecycle of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    if request.method == 'POST':
        if request.POST["action"] == "DEMOTE":
            obj.demote()
        elif request.POST["action"] == "PROMOTE":
            obj.promote()
    
    state = obj.state.name
    object_lifecycle = []
    for st in obj.lifecycle:
        object_lifecycle.append((st, st == state))
    is_signer = obj.check_permission(obj.get_current_sign_level(), False)
    is_signer_dm = obj.check_permission(obj.get_previous_sign_level(), False)
    ctx.update({'current_page':'lifecycle', 
                'object_lifecycle': object_lifecycle,
                'is_signer' : is_signer, 
                'is_signer_dm' : is_signer_dm})
    return r2r('DisplayObjectLifecycle.htm', ctx, request)

##########################################################################################
@handle_errors
def display_object_revisions(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays all revisions of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if obj.is_revisable():
        if request.method == "POST" and request.POST:
            add_form = AddRevisionForm(request.POST)
            if add_form.is_valid():
                obj.revise(add_form.cleaned_data["revision"])
        else:
            add_form = AddRevisionForm({"revision" : get_next_revision(obj_revi)})
        ctx["add_revision_form"] = add_form
    revisions = obj.get_all_revisions()
    ctx.update({'current_page' : 'revisions',
                'revisions' : revisions,
                })
    return r2r('DisplayObjectRevisions.htm', ctx, request)

##########################################################################################
@handle_errors
def display_object_history(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the history of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    history = obj.HISTORY.objects.filter(plmobject=obj.object).order_by('-date')
    ctx.update({'current_page' : 'history', 
                'object_history' : list(history)})
    return r2r('DisplayObjectHistory.htm', ctx, request)

#############################################################################################
###         All functions which manage the different html pages specific to part          ###
#############################################################################################
@handle_errors
def display_object_child(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the chidren of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_children"):
        # TODO
        raise TypeError()
    date = None
    level = "first"
    if request.GET:
        display_form = DisplayChildrenForm(request.GET)
        if display_form.is_valid():
            date = display_form.cleaned_data["date"]
            level = display_form.cleaned_data["level"]
    else:
        display_form = DisplayChildrenForm(initial={"date" : datetime.datetime.now(),
                                                    "level" : "first"})
    max_level = 1 if level == "first" else -1
    children = obj.get_children(max_level, date=date)
    if level == "last" and children:
        maximum = max(children, key=attrgetter("level")).level
        children = (c for c in children if c.level == maximum)
    # convert level to html space
    #children = (("&nbsp;" * 2 * (level-1), link) for level, link in children)

    ctx.update({'current_page':'BOM-child',
                'children': children,
                "display_form" : display_form})
    return r2r('DisplayObjectChild.htm', ctx, request)

##########################################################################################
@handle_errors(undo="..")
def edit_children(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which edits the chidren of the selected object.
    Possibility to modify the `.ParentChildLink.order`, the `.ParentChildLink.quantity` and to
    desactivate the `.ParentChildLink`
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_children"):
        # TODO
        raise TypeError()
    if request.method == "POST":
        formset = get_children_formset(obj, request.POST)
        if formset.is_valid():
            obj.update_children(formset)
            return HttpResponseRedirect("..")
    else:
        formset = get_children_formset(obj)
    ctx.update({'current_page':'BOM-child',
                'children_formset': formset, })
    return r2r('DisplayObjectChildEdit.htm', ctx, request)

##########################################################################################    
@handle_errors
def add_children(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for chidren creation of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if request.POST:
        add_child_form = AddChildForm(request.POST)
        if add_child_form.is_valid():
            child_obj = get_obj_from_form(add_child_form, request.user)
            obj.add_child(child_obj,
                          add_child_form.cleaned_data["quantity"],
                          add_child_form.cleaned_data["order"])
            return HttpResponseRedirect(obj.plmobject_url + "BOM-child/") 
    else:
        add_child_form = AddChildForm()
        ctx.update({'current_page':'BOM-child'})
    ctx.update({'link_creation': True,
                'add_child_form': add_child_form,
                'attach' : (obj, "add_child")})
    return r2r('DisplayObjectChildAdd.htm', ctx, request)
    
##########################################################################################    
@handle_errors
def display_object_parents(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the parent of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_parents"):
        # TODO
        raise TypeError()
    date = None
    level = "first"
    if request.GET:
        display_form = DisplayChildrenForm(request.GET)
        if display_form.is_valid():
            date = display_form.cleaned_data["date"]
            level = display_form.cleaned_data["level"]
    else:
        display_form = DisplayChildrenForm(initial={"date" : datetime.datetime.now(),
                                                    "level" : "first"})
    max_level = 1 if level == "first" else -1
    parents = obj.get_parents(max_level, date=date)
    if level == "last" and parents:
        maximum = max(parents, key=attrgetter("level")).level
        parents = (c for c in parents if c.level == maximum)
    ctx.update({'current_page':'parents',
                'parents' :  parents,
                'display_form' : display_form, })
    return r2r('DisplayObjectParents.htm', ctx, request)

##########################################################################################
@handle_errors
def display_object_doc_cad(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the related documents and CAD of 
    the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_attached_documents"):
        # TODO
        raise TypeError()
    if request.method == "POST":
        formset = get_doc_cad_formset(obj, request.POST)
        if formset.is_valid():
            obj.update_doc_cad(formset)
            return HttpResponseRedirect(".")
    else:
        formset = get_doc_cad_formset(obj)
    ctx.update({'current_page':'doc-cad',
                'object_doc_cad': obj.get_attached_documents(),
                'doc_cad_formset': formset})
    return r2r('DisplayObjectDocCad.htm', ctx, request)


##########################################################################################    
@handle_errors
def add_doc_cad(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for link creation (:class:`DocumentPartLink` link) between the selected object and some documents or CAD.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if request.POST:
        add_doc_cad_form = AddDocCadForm(request.POST)
        if add_doc_cad_form.is_valid():
            doc_cad_obj = get_obj_from_form(add_doc_cad_form, request.user)
            obj.attach_to_document(doc_cad_obj)
            return HttpResponseRedirect(obj.plmobject_url + "doc-cad/")
    else:
        add_doc_cad_form = AddDocCadForm()
    ctx.update({'link_creation': True,
                'add_doc_cad_form': add_doc_cad_form,
                'attach' : (obj, "attach_doc")})
    return r2r('DisplayDocCadAdd.htm', ctx, request)
    
#############################################################################################
###      All functions which manage the different html pages specific to documents        ###
#############################################################################################
@handle_errors
def display_related_part(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the related part of (:class:`DocumentPartLink` with) the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_attached_parts"):
        # TODO
        raise TypeError()
    if request.method == "POST":
        formset = get_rel_part_formset(obj, request.POST)
        if formset.is_valid():
            obj.update_rel_part(formset)
            return HttpResponseRedirect(".")
    else:
        formset = get_rel_part_formset(obj)
    ctx.update({'current_page':'parts', 
                'object_rel_part': obj.get_attached_parts(),
                'rel_part_formset': formset})
    return r2r('DisplayObjectRelPart.htm', ctx, request)

##########################################################################################    
@handle_errors
def add_rel_part(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for link creation (:class:`DocumentPartLink` link) between the selected object and some parts.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if request.POST:
        add_rel_part_form = AddRelPartForm(request.POST)
        if add_rel_part_form.is_valid():
            part_obj = get_obj_from_form(add_rel_part_form, request.user)
            obj.attach_to_part(part_obj)
            ctx.update({'add_rel_part_form': add_rel_part_form, })
            return HttpResponseRedirect(obj.plmobject_url + "parts/")
    else:
        add_rel_part_form = AddRelPartForm()
    ctx.update({'link_creation': True,
                'add_rel_part_form': add_rel_part_form,
                'attach' : (obj, "attach_part") })
    return r2r('DisplayRelPartAdd.htm', ctx, request)

##########################################################################################
@handle_errors
def display_files(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the files (:class:`DocumentFile`) uploaded in the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)

    if not hasattr(obj, "files"):
        raise TypeError()
    if request.method == "POST":
        formset = get_file_formset(obj, request.POST)
        if formset.is_valid():
            obj.update_file(formset)
            return HttpResponseRedirect(".")
    else:
        formset = get_file_formset(obj)
    ctx.update({'current_page':'files', 
                'file_formset': formset})
    return r2r('DisplayObjectFiles.htm', ctx, request)

##########################################################################################
@handle_errors(undo="..")
def add_file(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for the files (:class:`DocumentFile`) addition in the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if request.method == "POST":
        add_file_form = AddFileForm(request.POST, request.FILES)
        if add_file_form.is_valid():
            obj.add_file(request.FILES["filename"])
            ctx.update({'add_file_form': add_file_form, })
            return HttpResponseRedirect(obj.plmobject_url + "files/")
    else:
        add_file_form = AddFileForm()
    ctx.update({ 'add_file_form': add_file_form, })
    return r2r('DisplayFileAdd.htm', ctx, request)

#############################################################################################
###    All functions which manage the different html pages specific to part and document  ###
#############################################################################################
@handle_errors
def display_management(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the Users who manage the selected object (:class:`PLMObjectUserLink`).
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    object_management_list = models.PLMObjectUserLink.objects.filter(plmobject=obj)
    object_management_list = object_management_list.order_by("role")
    if not ctx["is_owner"]:
        link = object_management_list.filter(role="notified", user=request.user)
        ctx["is_notified"] = bool(link)
        if link:
            ctx["remove_notify_link"] = link[0]
        else:
            initial = { "type" : "User",
                        "username" : request.user.username
                      }
            form = SelectUserForm(initial=initial)
            for field in ("type", "username"):
                form.fields[field].widget = HiddenInput() 
            ctx["notify_self_form"] = form
    ctx.update({'current_page':'management',
                'object_management': object_management_list})
    
    return r2r('DisplayObjectManagement.htm', ctx, request)

##########################################################################################
@handle_errors(undo="../..")
def replace_management(request, obj_type, obj_ref, obj_revi, link_id):
    """
    Manage html page for the modification of the Users who manage the selected object (:class:`PLMObjectUserLink`).
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    :param link_id: :attr:`.PLMObjectUserLink.id`
    :type link_id: str
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    link = models.PLMObjectUserLink.objects.get(id=int(link_id))
    if obj.object.id != link.plmobject.id:
        raise ValueError("Bad link id")
    
    if request.method == "POST":
        replace_management_form = SelectUserForm(request.POST)
        if replace_management_form.is_valid():
            if replace_management_form.cleaned_data["type"] == "User":
                user_obj = get_obj_from_form(replace_management_form, request.user)
                obj.set_role(user_obj.object, link.role)
                if link.role == 'notified':
                    obj.remove_notified(link.user)
            return HttpResponseRedirect("../..")
    else:
        replace_management_form = SelectUserForm()
    
    ctx.update({'current_page':'management', 
                'replace_management_form': replace_management_form,
                'link_creation': True,
                'attach' : (obj, "delegate")})
    return r2r('DisplayObjectManagementReplace.htm', ctx, request)

##########################################################################################    
@handle_errors(undo="../..")
def add_management(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for the addition of a "notification" link
    (:class:`PLMObjectUserLink`) between some Users and the selected object. 
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if request.method == "POST":
        add_management_form = SelectUserForm(request.POST)
        if add_management_form.is_valid():
            if add_management_form.cleaned_data["type"] == "User":
                user_obj = get_obj_from_form(add_management_form, request.user)
                obj.set_role(user_obj.object, "notified")
            return HttpResponseRedirect("..")
    else:
        add_management_form = SelectUserForm()
    
    ctx.update({'current_page':'management', 
                'replace_management_form': add_management_form,
                'link_creation': True,
                "attach" : (obj, "delegate")})
    return r2r('DisplayObjectManagementReplace.htm', ctx, request)

##########################################################################################    
@handle_errors
def delete_management(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for the deletion of a "notification" link (:class:`PLMObjectUserLink`) between some Users and the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj = get_obj(obj_type, obj_ref, obj_revi, request.user)
    if request.method == "POST":
        try:
            link_id = request.POST["link_id"]
            link = models.PLMObjectUserLink.objects.get(id=int(link_id))
            obj.remove_notified(link.user)
        except (KeyError, ValueError, ControllerError):
            return HttpResponseForbidden()
    return HttpResponseRedirect("../")

##########################################################################################
###    Manage html pages for part / document creation and modification                 ###
##########################################################################################
def get_non_modifyable_attributes(obj, user, cls=models.PLMObject):
    """
    Create a list of object's attributes we can't modify' and set them a value
    
    Example::
        >>> MyClass
        <class 'openPLM.plmapp.models.Part'>
        >>> get_non_modifyable_attributes(MyClass)
        [('owner', 'Person'),
         ('creator', 'Person'),
         ('ctime', 'Date'),
         ('mtime', 'Date')]
    
    :param cls: :class: instance of `models.PLMObject`
    :return: list
    """
    non_modifyable_fields = cls.excluded_creation_fields()
    non_modifyable_attributes = []
    if obj == 'create':
        for field in non_modifyable_fields:
            if field in ('ctime', 'mtime'):
                non_modifyable_attributes.append(('datetime', field,
                    datetime.datetime.now()))
            elif field in ('owner', 'creator'):
                non_modifyable_attributes.append(('User', field,
                    user.username))
            elif field == 'state':
                non_modifyable_attributes.append(('State', field,
                    models.get_default_state()))
    else:
        for field in non_modifyable_fields:
            value = getattr(obj, field)
            if isinstance(value, datetime.datetime):
                non_modifyable_attributes.append(('datetime', field, value))
            elif isinstance(value, User):
                non_modifyable_attributes.append(('User', field, value.username))
            elif isinstance(value, models.State):
                non_modifyable_attributes.append(('State', field, value.name))
    return non_modifyable_attributes

##########################################################################################
@handle_errors
def create_object(request):
    """
    Manage html page for the creation of an instance of `models.PLMObject` subclass.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :return: a :class:`django.http.HttpResponse`
    """

    obj, ctx = get_generic_data(request)
    
    if request.method == 'GET':
        type_form = TypeForm(request.GET)
        if type_form.is_valid():
            cls = models.get_all_userprofiles_and_plmobjects()[type_form.cleaned_data["type"]]
            if issubclass(cls, models.Document):
                class_for_div="ActiveBox4Doc"
            else:
                class_for_div="ActiveBox4Part"
            data = {'revision':'a',
                    'lifecycle': str(models.get_default_lifecycle()), }
            creation_form = get_creation_form(request.user, cls, data, True)
            non_modifyable_attributes = get_non_modifyable_attributes('create', request.user, cls)
    elif request.method == 'POST':
        type_form = TypeForm(request.POST)
        if type_form.is_valid():
            type_name = type_form.cleaned_data["type"]
            cls = models.get_all_userprofiles_and_plmobjects()[type_name]
            if issubclass(cls, models.Document):
                class_for_div="ActiveBox4Doc"
            else:
                class_for_div="ActiveBox4Part"
            non_modifyable_attributes = get_non_modifyable_attributes('create', request.user, cls)
            creation_form = get_creation_form(request.user, cls, request.POST)
            if creation_form.is_valid():
                user = request.user
                controller_cls = get_controller(type_name)
                controller = controller_cls.create_from_form(creation_form, user)
                return HttpResponseRedirect(controller.plmobject_url)
    ctx.update({'class4div': class_for_div,
                'creation_form': creation_form,
                'object_type': type_form.cleaned_data["type"],
                'non_modifyable_attributes': non_modifyable_attributes })
    return r2r('DisplayObject4creation.htm', ctx, request)

##########################################################################################
@handle_errors
def modify_object(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page for the modification of the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    cls = models.get_all_plmobjects()[obj_type]
    non_modifyable_attributes = get_non_modifyable_attributes(obj, request.user, cls)
    if request.method == 'POST' and request.POST:
        modification_form = get_modification_form(cls, request.POST)
        if modification_form.is_valid():
            obj.update_from_form(modification_form)
            return HttpResponseRedirect(obj.plmobject_url)
    else:
        modification_form = get_modification_form(cls, instance=obj.object)
    
    ctx.update({'modification_form': modification_form,
                'non_modifyable_attributes': non_modifyable_attributes})
    return r2r('DisplayObject4modification.htm', ctx, request)

#############################################################################################
###         All functions which manage the different html pages specific to user          ###
#############################################################################################
@handle_errors
def modify_user(request, obj_ref):
    """
    Manage html page for the modification of the selected
    :class:`~django.contrib.auth.models.User`.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param obj_type: :class:`~django.contrib.auth.models.User`
    :return: a :class:`django.http.HttpResponse`
    """
    obj, ctx = get_generic_data(request, "User", obj_ref)
    if obj.object != request.user:
        raise PermissionError("You are not the user")
    class_for_div="ActiveBox4User"
    if request.method == 'POST' and request.POST:
        modification_form = OpenPLMUserChangeForm(request.POST)
        if modification_form.is_valid():
            obj.update_from_form(modification_form)
            return HttpResponseRedirect("/user/%s/" % obj.username)
    else:
        modification_form = OpenPLMUserChangeForm(instance=obj.object)
    
    ctx.update({'class4div': class_for_div, 'modification_form': modification_form})
    return r2r('DisplayObject4modification.htm', ctx, request)
    
##########################################################################################
@handle_errors
def change_user_password(request, obj_ref):
    """
    Manage html page for the modification of the selected
    :class:`~django.contrib.auth.models.User` password.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param obj_ref: :attr:`~django.contrib.auth.models.User.username`
    :return: a :class:`django.http.HttpResponse`
    """
    if request.user.username=='test':
        return HttpResponseRedirect("/user/%s/attributes/" % request.user)
    obj, ctx = get_generic_data(request, "User", obj_ref)
    if obj.object != request.user:
        raise PermissionError("You are not the user")

    if request.method == 'POST' and request.POST:
        modification_form = PasswordChangeForm(obj, request.POST)
        if modification_form.is_valid():
            obj.set_password(modification_form.cleaned_data['new_password2'])
            obj.save()
            return HttpResponseRedirect("/user/%s/" % obj.username)
    else:
        modification_form = PasswordChangeForm(obj)
    
    ctx.update({'class4div': "ActiveBox4User",
                'modification_form': modification_form})
    return r2r('DisplayObject4PasswordModification.htm', ctx, request)

#############################################################################################
@handle_errors
def display_related_plmobject(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays the related parts and related documents of (:class:`PLMObjectUserLink` with) the selected :class:`~django.contrib.auth.models.User`.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    
    if not hasattr(obj, "get_object_user_links"):
        # TODO
        raise TypeError()
    ctx.update({'current_page':'parts-doc-cad',
                'object_user_link': obj.get_object_user_links()})
    
    return r2r('DisplayObjectRelPLMObject.htm', ctx, request)

#############################################################################################
@handle_errors
def display_delegation(request, obj_ref):
    """
    Manage html page which displays the delegations of the selected 
    :class:`~django.contrib.auth.models.User`.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param obj_ref: :attr:`~django.contrib.auth.models.User.username`
    :type obj_ref: str
    :return: a :class:`django.http.HttpResponse`
    """
    obj, ctx = get_generic_data(request, "User", obj_ref)
    
    if not hasattr(obj, "get_user_delegation_links"):
        # TODO
        raise TypeError()
    if request.method == "POST":
        selected_link_id = request.POST.get('link_id')
        obj.remove_delegation(models.DelegationLink.objects.get(pk=int(selected_link_id)))
    ctx.update({'current_page':'delegation', 
                'user_delegation_link': obj.get_user_delegation_links()})
    
    return r2r('DisplayObjectDelegation.htm', ctx, request)


##########################################################################################    
@handle_errors(undo="../../..")
def delegate(request, obj_ref, role, sign_level):
    """
    Manage html page for delegations modification of the selected
    :class:`~django.contrib.auth.models.User`.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param obj_type: :class:`~django.contrib.auth.models.User`
    :type obj_ref: str
    :param role: :attr:`.DelegationLink.role` if role is not "sign"
    :type role: str
    :param sign_level: used for :attr:`.DelegationLink.role` if role is "sign"
    :type sign_level: str
    :return: a :class:`django.http.HttpResponse`
    """
    obj, ctx = get_generic_data(request, "User", obj_ref)
    
    if request.method == "POST":
        delegation_form = SelectUserForm(request.POST)
        if delegation_form.is_valid():
            if delegation_form.cleaned_data["type"] == "User":
                user_obj = get_obj_from_form(delegation_form, request.user)
                if role == "notified" or role == "owner":
                    obj.delegate(user_obj.object, role)
                    return HttpResponseRedirect("../..")
                elif role == "sign":
                    if sign_level == "all":
                        obj.delegate(user_obj.object, "sign*")
                        return HttpResponseRedirect("../../..")
                    elif sign_level.isdigit():
                        obj.delegate(user_obj.object, level_to_sign_str(int(sign_level)-1))
                        return HttpResponseRedirect("../../..")
    else:
        delegation_form = SelectUserForm()
    if role == 'sign':
        if sign_level.isdigit():
            role = _("signer level") + " " + str(sign_level)
        else:
            role = _("signer all levels")
    elif role == "notified":
        role = _("notified")
    
    ctx.update({'current_page':'delegation',
                'replace_management_form': delegation_form,
                'link_creation': True,
                'attach' : (obj, "delegate"),
                'role': role})
    return r2r('DisplayObjectManagementReplace.htm', ctx, request)
    
##########################################################################################    
@handle_errors
def stop_delegate(request, obj_ref, role, sign_level):
    """
    Manage html page to stop delegations of (:class:`DelegationLink` with) the selected :class:`~django.contrib.auth.models.User`.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param obj_ref: :attr:`~django.contrib.auth.models.User.username`
    :type obj_ref: str
    :param role: :attr:`.DelegationLink.role` if role is not "sign"
    :type role: str
    :param sign_level: used for :attr:`.DelegationLink.role` if role is "sign"
    :type sign_level: str
    :return: a :class:`django.http.HttpResponse`
    """
    obj, ctx = get_generic_data(request, "User", obj_ref)
    
    if request.method == "POST":
        delegation_form = SelectUserForm(request.POST)
        if delegation_form.is_valid():
            if delegation_form.cleaned_data["type"] == "User":
                user_obj = get_obj_from_form(delegation_form, request.user)
                if role == "notified":
                    obj.set_role(user_obj.object, "notified")
                    return HttpResponseRedirect("..")
                elif role == "owner":
                    return HttpResponseRedirect("..")
                elif role == "sign":
                    if sign_level == "all":
                        return HttpResponseRedirect("..")
                    elif sign_level.is_digit():
                        return HttpResponseRedirect("../..")
    else:
        delegation_form = SelectUserForm()
    action_message_string = _("Select the user you no longer want for your \"%s\" role delegation :") % role
    
    ctx.update({'current_page':'parts-doc-cad',
                'replace_management_form': delegation_form,
                'action_message': action_message_string})
    return r2r('DisplayObjectManagementReplace.htm', ctx, request)
    
##########################################################################################
###             Manage html pages for file check-in / check-out / download             ###
##########################################################################################    
@handle_errors
def checkin_file(request, obj_type, obj_ref, obj_revi, file_id_value):
    """
    Manage html page for the files (:class:`DocumentFile`) checkin in the selected object.
    It computes a context dictionnary based on
    
    .. include:: views_params.txt 
    :param file_id_value: :attr:`.DocumentFile.id`
    :type file_id_value: str
    :return: a :class:`django.http.HttpResponse`
    """
    obj, ctx = get_generic_data(request, obj_type, obj_ref, obj_revi)
    if request.POST:
        checkin_file_form = AddFileForm(request.POST, request.FILES)
        if checkin_file_form.is_valid():
            obj.checkin(models.DocumentFile.objects.get(id=file_id_value),
                        request.FILES["filename"])
            return HttpResponseRedirect(obj.plmobject_url + "files/")
    else:
        checkin_file_form = AddFileForm()
    ctx['add_file_form'] =  checkin_file_form
    return r2r('DisplayFileAdd.htm', ctx, request)

##########################################################################################
@handle_errors 
def download(request, docfile_id, filename=""):
    """
    Manage html page for the files (:class:`DocumentFile`) download in the selected object.
    It computes a context dictionnary based on
    
    :param request: :class:`django.http.QueryDict`
    :param docfile_id: :attr:`.DocumentFile.id`
    :type docfile_id: str
    :return: a :class:`django.http.HttpResponse`
    """
    doc_file = models.DocumentFile.objects.get(id=docfile_id)
    ctrl = get_obj_by_id(int(doc_file.document.id), request.user)
    ctrl.check_readable()
    name = doc_file.filename.encode("utf-8", "ignore")
    mimetype = guess_type(name, False)[0]
    if not mimetype:
        mimetype = 'application/octet-stream'
    response = HttpResponse(file(doc_file.file.path), mimetype=mimetype)
    response["Content-Length"] = doc_file.file.size
    if not filename:
        response['Content-Disposition'] = 'attachment; filename="%s"' % name
    return response
 
##########################################################################################
@handle_errors 
def checkout_file(request, obj_type, obj_ref, obj_revi, docfile_id):
    """
    Manage html page for the files (:class:`DocumentFile`) checkout from the selected object.
    It locks the :class:`DocumentFile` and, after, calls :func:`.views.download`
    
    .. include:: views_params.txt 
    :param docfile_id: :attr:`.DocumentFile.id`
    :type docfile_id_value: str
    """
    obj = get_obj(obj_type, obj_ref, obj_revi, request.user)
    doc_file = models.DocumentFile.objects.get(id=docfile_id)
    obj.lock(doc_file)
    return download(request, docfile_id)

##########################################################################################
###                     Manage html pages for navigate function                        ###
##########################################################################################    
@handle_errors
def navigate(request, obj_type, obj_ref, obj_revi):
    """
    Manage html page which displays a graphical picture the different links
    between :class:`~django.contrib.auth.models.User` and  :class:`.models.PLMObject`.
    This function uses Graphviz (http://graphviz.org/).
    Some filters let user defines which type of links he/she wants to display.
    It computes a context dictionary based on
    
    .. include:: views_params.txt 
    """
    ctx = get_navigate_data(request, obj_type, obj_ref, obj_revi)
    return r2r('Navigate.htm', ctx, request)

@handle_errors
def display_users(request, obj_ref):
    obj, ctx = get_generic_data(request, "Group", obj_ref)
    if request.method == "POST":
        formset = forms.get_user_formset(obj, request.POST)
        if formset.is_valid():
            obj.update_users(formset)
            return HttpResponseRedirect(".")
    else:
        formset = forms.get_user_formset(obj)
    ctx["user_formset"] = formset
    ctx['current_page'] = 'users' 
    ctx['in_group'] = bool(request.user.groups.filter(id=obj.id))
    return r2r("groups/users.htm", ctx, request)

@handle_errors
def group_add_user(request, obj_ref):
    """
    View of the *Add user* page of a group.

    """

    obj, ctx = get_generic_data(request, "Group", obj_ref)
    if request.method == "POST":
        form = SelectUserForm(request.POST)
        if form.is_valid():
            obj.add_user(User.objects.get(username=form.cleaned_data["username"]))
            return HttpResponseRedirect("..")
    else:
        form = forms.SelectUserForm()
    ctx["add_user_form"] = form
    ctx['current_page'] = 'users' 
    return r2r("groups/add_user.htm", ctx, request)

@handle_errors
def group_ask_to_join(request, obj_ref):
    obj, ctx = get_generic_data(request, "Group", obj_ref)
    if request.method == "POST":
        obj.ask_to_join()
        return HttpResponseRedirect("..")
    else:
        form = forms.SelectUserForm()
    ctx["ask_form"] = ""
    ctx['current_page'] = 'users' 
    ctx['in_group'] = bool(request.user.groups.filter(id=obj.id))
    return r2r("groups/ask_to_join.htm", ctx, request)

@handle_errors
def display_groups(request, obj_ref):
    """
    View of the *groups* page of an user.

    """

    obj, ctx = get_generic_data(request, "User", obj_ref)
    ctx['current_page'] = 'groups' 
    return r2r("users/groups.htm", ctx, request)

@handle_errors
def sponsor(request, obj_ref):
    obj, ctx = get_generic_data(request, "User", obj_ref)
    if request.method == "POST":
        form = forms.SponsorForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            obj.sponsor(new_user)
            return HttpResponseRedirect("..")
    else:
        form = SponsorForm(initial={"sponsor":obj.id}, sponsor=obj.id)
    ctx["sponsor_form"] = form
    ctx['current_page'] = 'delegation' 
    return r2r("users/sponsor.htm", ctx, request)

@handle_errors
def display_plmobjects(request, obj_ref):
    """
    View of the *objects* page of a group.
    """
    
    obj, ctx = get_generic_data(request, "Group", obj_ref)
    ctx["objects"] = obj.plmobject_group.all().order_by("type", "reference", "revision")
    ctx['current_page'] = 'groups'
    return r2r("groups/objects.htm", ctx, request)

@handle_errors(undo="../../../users/")
def accept_invitation(request, obj_ref, token):
    token = long(token)
    obj, ctx = get_generic_data(request, "Group", obj_ref)
    inv = models.Invitation.objects.get(token=token)
    if request.method == "POST":
        form = forms.InvitationForm(request.POST)
        if form.is_valid() and inv == form.cleaned_data["invitation"]:
            obj.accept_invitation(inv)
            return HttpResponseRedirect("../../../users/")
    else:
        form = forms.InvitationForm(initial={"invitation" : inv})
    ctx["invitation_form"] = form
    ctx['current_page'] = 'users'
    ctx["invitation"] = inv
    return r2r("groups/accept_invitation.htm", ctx, request)

 
@handle_errors(undo="../../../users/")
def refuse_invitation(request, obj_ref, token):
    token = long(token)
    obj, ctx = get_generic_data(request, "Group", obj_ref)
    inv = models.Invitation.objects.get(token=token)
    if request.method == "POST":
        form = forms.InvitationForm(request.POST)
        if form.is_valid() and inv == form.cleaned_data["invitation"]:
            obj.refuse_invitation(inv)
            return HttpResponseRedirect("../../../users/")
    else:
        form = forms.InvitationForm(initial={"invitation" : inv})
    ctx["invitation_form"] = form
    ctx["invitation"] = inv
    ctx['current_page'] = 'users'
    return r2r("groups/refuse_invitation.htm", ctx, request)

@handle_errors
def import_csv_init(request):
    obj, ctx = get_generic_data(request)
    if request.method == "POST":
        csv_form = CSVForm(request.POST, request.FILES)
        if csv_form.is_valid():
            f = request.FILES["file"]
            prefix = "openplmcsv"
            tmp = tempfile.NamedTemporaryFile(prefix=prefix, delete=False)
            for chunk in f.chunks():
                tmp.write(chunk)
            name = os.path.split(tmp.name)[1][len(prefix):]
            tmp.close()
            encoding = csv_form.cleaned_data["encoding"]
            return HttpResponseRedirect("/import/csv/%s/%s/" % (name, encoding))
    else:
        csv_form = CSVForm()
    ctx["csv_form"] = csv_form
    ctx["step"] = 1
    return r2r("import/csv.htm", ctx, request)

@handle_errors
def import_csv_apply(request, filename, encoding):
    obj, ctx = get_generic_data(request)
    ctx["encoding_error"] = False
    ctx["io_error"] = False
    try:
        path = os.path.join(tempfile.gettempdir(), "openplmcsv" +  filename)
        with open(path, "rb") as csv_file:
            preview = csvimport.CSVPreview(csv_file, encoding)
        if request.method == "POST":
            headers_formset = forms.HeadersFormset(request.POST)
            if headers_formset.is_valid():
                headers = headers_formset.headers
                try:
                    with open(path, "rb") as csv_file:
                        csvimport.import_csv(csv_file, headers, request.user,
                                             encoding)
                except csvimport.CSVImportError as exc:
                    ctx["errors"] = exc.errors.iteritems()
                else:
                    os.remove(path)
                    return HttpResponseRedirect("/import/done/")
        else:
            initial = [{"header": header} for header in preview.guessed_headers]
            headers_formset = forms.HeadersFormset(initial=initial)
        ctx.update({
            "preview" :  preview,
            "preview_data" : itertools.izip((f["header"] for f in headers_formset.forms),
                preview.headers, *preview.rows),
            "headers_formset" : headers_formset,
        })
    except UnicodeError:
        ctx["encoding_error"] = True
    except (IOError, csv.Error):
        ctx["io_error"] = True
    ctx["has_critical_error"] = ctx["io_error"] or ctx["encoding_error"] \
            or "errors" in ctx
    ctx["csv_form"] = CSVForm(initial={"encoding" : encoding})
    ctx["step"] = 2
    return r2r("import/csv.htm", ctx, request)


@handle_errors
def import_csv_done(request):
    obj, ctx = get_generic_data(request)
    return r2r("import/done.htm", ctx, request)

