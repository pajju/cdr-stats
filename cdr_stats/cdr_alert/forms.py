#
# CDR-Stats License
# http://www.cdr-stats.org
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2011-2012 Star2Billing S.L.
#
# The Initial Developer of the Original Code is
# Arezqui Belaid <info@star2billing.com>
#

from django import forms
from django.forms import ModelForm
from django.contrib.auth.models import User
from django.contrib.admin.widgets import *
from django.utils.translation import ugettext_lazy as _
from cdr_alert.models import *
from cdr.functions_def import get_country_list
# place form definition here


class BWCountryForm(forms.Form):
    """Blacklist/Whitelist by country form"""
    country = forms.ChoiceField(label=_('Country'), required=True,
                                choices=get_country_list())

    def __init__(self, *args, **kwargs):
        super(BWCountryForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder = ['country',]

