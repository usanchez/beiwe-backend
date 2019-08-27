import json
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from flask import (abort, Blueprint, flash, redirect, render_template, request,
    session)

from config.constants import CHECKBOX_TOGGLES, TIMER_VALUES
from database.study_models import Study, StudyField
from database.user_models import Researcher, Participant, ParticipantFieldValue
from libs.admin_authentication import (authenticate_site_admin,
    get_researcher_allowed_studies, researcher_is_site_admin,
    authenticate_researcher_study_access, SESSION_NAME)
from libs.copy_study import copy_existing_study_if_asked_to
from libs.http_utils import checkbox_to_boolean, string_to_int

system_admin_pages = Blueprint('system_admin_pages', __name__)

# TODO: Document.


@system_admin_pages.route('/manage_researchers', methods=['GET'])
@authenticate_site_admin
def manage_researchers():
    researcher_list = []
    for researcher in Researcher.get_all_researchers_by_username():
        allowed_studies = Study.get_all_studies_by_name().filter(researchers=researcher).values_list('name', flat=True)
        researcher_list.append((researcher.as_native_python(), list(allowed_studies)))

    return render_template(
        'manage_researchers.html',
        admins=json.dumps(researcher_list),
        allowed_studies=get_researcher_allowed_studies(),
        site_admin=researcher_is_site_admin()
    )


@system_admin_pages.route('/edit_researcher/<string:researcher_pk>', methods=['GET', 'POST'])
@authenticate_site_admin
def edit_researcher(researcher_pk):
    researcher = Researcher.objects.get(pk=researcher_pk)
    admin_is_current_user = (researcher.username == session[SESSION_NAME])
    current_studies = Study.get_all_studies_by_name().filter(researchers=researcher)
    return render_template(
        'edit_researcher.html',
        admin=researcher,
        current_studies=current_studies,
        all_studies=Study.get_all_studies_by_name(),
        allowed_studies=get_researcher_allowed_studies(),
        admin_is_current_user=admin_is_current_user,
        site_admin=researcher_is_site_admin(),
        redirect_url='/edit_researcher/{:s}'.format(researcher_pk),
    )


@system_admin_pages.route('/create_new_researcher', methods=['GET', 'POST'])
@authenticate_site_admin
def create_new_researcher():
    if request.method == 'GET':
        return render_template(
            'create_new_researcher.html',
            allowed_studies=get_researcher_allowed_studies(),
            site_admin=researcher_is_site_admin()
        )

    # Drop any whitespace or special characters from the username
    username = ''.join(e for e in request.form.get('admin_id', '') if e.isalnum())
    password = request.form.get('password', '')

    if Researcher.objects.filter(username=username).exists():
        flash("There is already a researcher with username " + username, 'danger')
        return redirect('/create_new_researcher')
    else:
        researcher = Researcher.create_with_password(username, password)
        return redirect('/edit_researcher/{:d}'.format(researcher.pk))


"""########################### Study Pages ##################################"""


@system_admin_pages.route('/manage_studies', methods=['GET'])
@authenticate_site_admin
def manage_studies():
    studies = [study.as_native_python() for study in Study.get_all_studies_by_name()]
    return render_template(
        'manage_studies.html',
        studies=json.dumps(studies),
        allowed_studies=get_researcher_allowed_studies(),
        site_admin=researcher_is_site_admin()
    )


@system_admin_pages.route('/edit_study/<string:study_id>', methods=['GET'])
@authenticate_site_admin
def edit_study(study_id=None):
    study = Study.objects.get(pk=study_id)
    all_researchers = Researcher.get_all_researchers_by_username()
    return render_template(
        'edit_study.html',
        study=study,
        all_researchers=all_researchers,
        allowed_studies=get_researcher_allowed_studies(),
        site_admin=researcher_is_site_admin(),
        redirect_url='/edit_study/{:s}'.format(study_id),
    )


@system_admin_pages.route('/study_fields/<string:study_id>', methods=['GET', 'POST'])
@authenticate_site_admin
def study_fields(study_id=None):
    study = Study.objects.get(pk=study_id)

    if request.method == 'GET':
        return render_template(
            'study_custom_fields.html',
            study=study,
            fields=study.fields.all(),
            allowed_studies=get_researcher_allowed_studies(),
            site_admin=researcher_is_site_admin(),
        )

    new_field = request.values.get('new_field', None)
    if new_field:
        StudyField.objects.get_or_create(study=study, field_name=new_field)

    return redirect('/study_fields/{:d}'.format(study.id))


@system_admin_pages.route('/delete_field/<string:study_id>', methods=['POST'])
@authenticate_site_admin
def delete_field(study_id=None):
    study = Study.objects.get(pk=study_id)

    field = request.values.get('field', None)
    if field:
        try:
            study_field = StudyField.objects.get(study=study, id=field)
        except StudyField.DoesNotExist:
            study_field = None

        try:
            if study_field:
                study_field.delete()
        except ProtectedError:
            flash("This field can not be removed because it is already in use", 'danger')

    return redirect('/study_fields/{:d}'.format(study.id))


@system_admin_pages.route('/create_study', methods=['GET', 'POST'])
@authenticate_site_admin
def create_study():
    if request.method == 'GET':
        studies = [study.as_native_python() for study in Study.get_all_studies_by_name()]
        return render_template(
            'create_study.html',
            studies=json.dumps(studies),
            allowed_studies=get_researcher_allowed_studies(),
            site_admin=researcher_is_site_admin()
        )

    name = request.form.get('name', '')
    encryption_key = request.form.get('encryption_key', '')
    
    is_test = request.form.get('is_test') == 'true'  # 'true' -> True, 'false' -> False
    try:
        study = Study.create_with_object_id(name=name, encryption_key=encryption_key, is_test=is_test)
        copy_existing_study_if_asked_to(study)
        flash('Successfully created study {}.'.format(name), 'success')
        return redirect('/device_settings/{:d}'.format(study.pk))
    except ValidationError as ve:
        for field, message in ve.message_dict.iteritems():
            flash('{}: {}'.format(field, message[0]), 'danger')
        return redirect('/create_study')


@system_admin_pages.route('/delete_study/<string:study_id>', methods=['POST'])
@authenticate_site_admin
def delete_study(study_id=None):
    """ This functionality has been disabled pending testing and feature change."""
    if request.form.get('confirmation', 'false') == 'true':
        study = Study.objects.get(pk=study_id)
        study.mark_deleted()
        flash("Deleted study '%s'" % study.name, 'success')
        return "success"


@system_admin_pages.route('/device_settings/<string:study_id>', methods=['GET', 'POST'])
@authenticate_researcher_study_access
def device_settings(study_id=None):
    study = Study.objects.get(pk=study_id)
    readonly = not researcher_is_site_admin()

    if request.method == 'GET':
        settings = study.get_study_device_settings()
        return render_template(
            "device_settings.html",
            study=study.as_native_python(),
            settings=settings.as_native_python(),
            readonly=readonly,
            allowed_studies=get_researcher_allowed_studies(),
            site_admin=researcher_is_site_admin()
        )
    
    if readonly:
        abort(403)
        
    settings = study.get_study_device_settings()
    params = {k:v for k,v in request.values.iteritems() if not k.startswith("consent_section")}
    consent_sections = {k: v for k, v in request.values.iteritems() if k.startswith("consent_section")}
    params = checkbox_to_boolean(CHECKBOX_TOGGLES, params)
    params = string_to_int(TIMER_VALUES, params)
    # the ios consent sections are a json field but the frontend returns something weird,
    # see the documentation in unflatten_consent_sections for details
    params["consent_sections"] = json.dumps(unflatten_consent_sections(consent_sections))
    settings.update(**params)
    return redirect('/edit_study/{:d}'.format(study.id))


def unflatten_consent_sections(consent_sections_dict):
    # consent_sections is a flat structure with structure like this:
    # { 'label_ending_in.text': 'text content',  'label_ending_in.more': 'more content' }
    # we need to transform it into a nested structure like this:
    # { 'label': {'text':'text content',  'more':'more content' }
    refactored_consent_sections = defaultdict(dict)
    for key, content in consent_sections_dict.iteritems():
        _, label, content_type = key.split(".")
        print _, label, content_type
        refactored_consent_sections[label][content_type] = content
    return dict(refactored_consent_sections)
