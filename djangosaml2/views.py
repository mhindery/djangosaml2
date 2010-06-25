# Copyright (C) 2009 Lorenzo Gil Sanchez
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#            http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy

from django.conf import settings
from django.contrib import auth
from django.http import HttpResponse, HttpResponseRedirect

from saml2.client import Saml2Client
from saml2.config import Config
from saml2.metadata import entity_descriptor, entities_descriptor
from saml2.sigver import SecurityContext

from djangosaml2.models import OutstandingQuery


def _load_conf():
    conf = Config()
    conf.load(copy.deepcopy(settings.SAML_CONFIG))
    return conf


def login(request):
    next = request.GET.get('next', '/')
    conf = _load_conf()
    srv = conf['service']['sp']
    idp_url = srv['idp'].values()[0]
    client = Saml2Client(None, conf)

    (session_id, result) = client.authenticate(
        spentityid=conf['entityid'],
        location=idp_url,
        service_url=srv['url'],
        my_name=srv['name'],
        relay_state=next)

    OutstandingQuery.objects.create(session_id=session_id,
                                    came_from=next)

    redirect_url = result[1]
    return HttpResponseRedirect(redirect_url)


def assertion_consumer_service(request):
    conf = _load_conf()
    post = {'SAMLResponse': request.POST['SAMLResponse']}
    client = Saml2Client(None, conf)
    response = client.response(post, conf['entityid'],
                               OutstandingQuery.objects.as_dict())
    OutstandingQuery.objects.clear_session(response.session_id())

    user = auth.authenticate(session_info=response.session_info())
    if user is None:
        return HttpResponse("user not valid")

    auth.login(request, user)
    relay_state = request.POST.get('RelayState', '/')
    return HttpResponseRedirect(relay_state)


def metadata(request):
    ed_id = getattr(settings, 'SAML_METADATA_ID', '')
    name = getattr(settings, 'SAML_METADATA_NAME', '')
    sign = getattr(settings, 'SAML_METADATA_SIGN', False)
    conf = _load_conf()
    valid_for = conf.get('valid_for', 24)
    output = entities_descriptor([entity_descriptor(conf, valid_for)],
                                 valid_for, name, ed_id, sign,
                                 SecurityContext(conf.xmlsec(),
                                                 conf['key_file']))
    return HttpResponse(content=output, content_type="text/xml; charset=utf8")