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
from django.contrib import admin
from django.contrib import messages
from django.conf.urls.defaults import *
from django.utils.translation import ugettext as _
from django.db.models import *
from django.template import RequestContext
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from django.core.exceptions import ObjectDoesNotExist
from django.utils.safestring import mark_safe
from django.conf import settings

from pymongo.connection import Connection
from pymongo.errors import ConnectionFailure

from cdr.models import *
from cdr.forms import *
from cdr.functions_def import *
from cdr_alert.models import Blacklist, Whitelist
from cdr_alert.functions_blacklist import *

from country_dialcode.models import Prefix
from common.common_functions import striplist

from random import choice
from uuid import uuid1
from datetime import *
import calendar
import time
import sys
import random
import json, ast
import re
import csv

# Assign collection names to variables
CDR_COMMON = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_COMMON]
CDR_MONTHLY = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_MONTHLY]
CDR_DAILY = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_DAILY]
CDR_HOURLY = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_HOURLY]
CDR_COUNTRY_REPORT = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_COUNTRY_REPORT]

# Switch
class SwitchAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'ipaddress', 'key_uuid')
    list_filter = ['name', 'ipaddress',]
    search_fields = ('name', 'ipaddress',)

    def get_urls(self):
        urls = super(SwitchAdmin, self).get_urls()
        my_urls = patterns('',
            (r'^import_cdr/$',
             self.admin_site.admin_view(self.import_cdr)),
        )
        return my_urls + urls

    def import_cdr(self, request):
        """Add custom method in django admin view to import CSV file of
        cdr

        **Attributes**:

            * ``form`` - CDR_FileImport
            * ``template`` - admin/cdr/switch/import_contact.html

        **Logic Description**:


        **Important variable**:

            * total_rows - Total no. of records in the CSV file
            * retail_record_count - No. of records which are imported from
              The CSV file
        """
        opts = Switch._meta
        app_label = opts.app_label
        file_exts = ('.csv', )
        rdr = ''  # will contain CSV data
        msg = ''
        success_import_list = []
        error_import_list = []
        type_error_import_list = []
        if request.method == 'POST':
            form = CDR_FileImport(request.user, request.POST, request.FILES)

            if form.is_valid():

                cdr_field_list = {}
                cdr_field_not_in_list = []
                for i in CDR_FIELD_LIST:
                    if int(request.POST[i]) != 0:
                        cdr_field_list[i] = int(request.POST[i])
                    else:
                        cdr_field_not_in_list.append((i))

                # perform sorting & get unique order list
                countMap = {}
                for v in cdr_field_list.itervalues():
                    countMap[v] = countMap.get(v, 0) + 1
                uni = [ (k, v) for k, v in cdr_field_list.iteritems() if countMap[v] == 1]
                uni = sorted(uni, key=lambda uni: uni[1])

                # if order list matched with CDR_FIELD_LIST count
                if len(uni) == len(CDR_FIELD_LIST) - len(cdr_field_not_in_list):

                    # To count total rows of CSV file
                    records = csv.reader(request.FILES['csv_file'],
                                         delimiter=',', quotechar='"')
                    total_rows = len(list(records))

                    rdr = csv.reader(request.FILES['csv_file'],
                                     delimiter=',', quotechar='"')
                    cdr_record_count = 0

                    # Read each Row
                    for row in rdr:
                        if (row and str(row[0]) > 0):
                            row = striplist(row)
                            try:
                                accountcode = ''
                                # extra fields to import
                                caller_id_name = ''
                                direction = 'outbound'
                                remote_media_ip = ''
                                answer_uepoch = ''
                                end_uepoch = ''
                                mduration = ''
                                billmsec = ''
                                write_codec = ''
                                read_codec = ''
                                get_cdr_from_row = {}
                                row_counter = 0
                                for j in uni:
                                    get_cdr_from_row[j[0]] = row[j[1]-1]
                                    #get_cdr_from_row[j[0]] = row[row_counter]
                                    if j[0] == 'caller_id_name':
                                        caller_id_name = row[j[1]-1]
                                    if j[0] == 'caller_id_name':
                                        caller_id_name = row[j[1]-1]
                                    if j[0] == 'direction':
                                        direction = row[j[1]-1]
                                    if j[0] == 'remote_media_ip':
                                        remote_media_ip = row[j[1]-1]
                                    if j[0] == 'answer_uepoch':
                                        answer_uepoch = row[j[1]-1]
                                    if j[0] == 'end_uepoch':
                                        end_uepoch = row[j[1]-1]
                                    if j[0] == 'mduration':
                                        mduration = row[j[1]-1]
                                    if j[0] == 'billmsec':
                                        billmsec = row[j[1]-1]
                                    if j[0] == 'read_codec':
                                        read_codec = row[j[1]-1]
                                    if j[0] == 'write_codec':
                                        write_codec = row[j[1]-1]

                                    row_counter = row_counter + 1

                                get_cdr_not_from_row = {}
                                if len(cdr_field_not_in_list) != 0:
                                    for i in cdr_field_not_in_list:
                                        if i == 'accountcode':
                                            accountcode = int(request.POST[i+"_csv"])

                                if not accountcode:
                                    accountcode = int(get_cdr_from_row['accountcode'])


                                # Mandatory fields to import
                                switch_id = int(request.POST['switch'])
                                caller_id_number = get_cdr_from_row['caller_id_number']
                                duration = int(get_cdr_from_row['duration'])
                                billsec = int(get_cdr_from_row['billsec'])
                                hangup_cause_id = get_hangupcause_id(int(get_cdr_from_row['hangup_cause_id']))
                                start_uepoch = datetime.fromtimestamp(int(get_cdr_from_row['start_uepoch']))
                                destination_number = get_cdr_from_row['destination_number']
                                uuid = get_cdr_from_row['uuid']

                                # number startswith 0 or `+` sign
                                #remove leading +
                                sanitized_destination = re.sub("^\++", "", destination_number)
                                #remove leading 011
                                sanitized_destination = re.sub("^011+", "", sanitized_destination)
                                #remove leading 00
                                sanitized_destination = re.sub("^0+", "", sanitized_destination)

                                prefix_list = prefix_list_string(sanitized_destination)

                                authorized = 1 # default
                                #check desti against whiltelist
                                authorized = chk_prefix_in_whitelist(prefix_list)
                                if authorized:
                                    authorized = 1 # allowed destination
                                else:
                                    #check desti against blacklist
                                    authorized = chk_prefix_in_blacklist(prefix_list)
                                    if not authorized:
                                        authorized = 0 # not allowed destination

                                country_id = get_country_id(prefix_list)

                                # Extra fields to import
                                if answer_uepoch:
                                    answer_uepoch = datetime.fromtimestamp(int(answer_uepoch[:10]))
                                if end_uepoch:
                                    end_uepoch = datetime.fromtimestamp(int(end_uepoch[:10]))

                                # Prepare global CDR
                                cdr_record = {
                                    'switch_id': int(request.POST['switch']),
                                    'caller_id_number': caller_id_number,
                                    'caller_id_name': caller_id_name,
                                    'destination_number': destination_number,
                                    'duration': duration,
                                    'billsec': billsec,
                                    'hangup_cause_id': hangup_cause_id,
                                    'accountcode': accountcode,
                                    'direction': direction,
                                    'uuid': uuid,
                                    'remote_media_ip': remote_media_ip,
                                    'start_uepoch': start_uepoch,
                                    'answer_uepoch': answer_uepoch,
                                    'end_uepoch': end_uepoch,
                                    'mduration': mduration,
                                    'billmsec': billmsec,
                                    'read_codec': read_codec,
                                    'write_codec': write_codec,
                                    'cdr_type': 'CSV_IMPORT',
                                    'cdr_object_id': '',
                                    'country_id': country_id,
                                    'authorized': authorized,
                                    }

                                try:
                                    # check if cdr is already existing in cdr_common
                                    cdr_data = settings.DB_CONNECTION[settings.CDR_MONGO_CDR_COMMON]
                                    query_var = {}
                                    query_var['uuid'] = uuid
                                    record_count = cdr_data.find(query_var).count()
                                    if record_count >= 1:
                                        msg = _('CDR already exists !!')
                                        error_import_list.append(row)
                                    else:
                                        # if not, insert record
                                        # record global CDR
                                        CDR_COMMON.insert(cdr_record)

                                        # monthly collection
                                        current_y_m = datetime.strptime(str(start_uepoch)[:7], "%Y-%m")
                                        CDR_MONTHLY.update(
                                                {
                                                'start_uepoch': current_y_m,
                                                'destination_number': destination_number,
                                                'hangup_cause_id': hangup_cause_id,
                                                'accountcode': accountcode,
                                                'switch_id': switch_id,
                                                },
                                                {
                                                '$inc':
                                                        {'calls': 1,
                                                         'duration': duration }
                                            }, upsert=True)

                                        # daily collection
                                        current_y_m_d = datetime.strptime(str(start_uepoch)[:10], "%Y-%m-%d")
                                        CDR_DAILY.update(
                                                {
                                                'start_uepoch': current_y_m_d,
                                                'destination_number': destination_number,
                                                'hangup_cause_id': hangup_cause_id,
                                                'accountcode': accountcode,
                                                'switch_id': switch_id,
                                                },
                                                {
                                                '$inc':
                                                        {'calls': 1,
                                                         'duration': duration }
                                            },upsert=True)

                                        # hourly collection
                                        current_y_m_d_h = datetime.strptime(str(start_uepoch)[:13], "%Y-%m-%d %H")
                                        CDR_HOURLY.update(
                                                {
                                                'start_uepoch': current_y_m_d_h,
                                                'destination_number': destination_number,
                                                'hangup_cause_id': hangup_cause_id,
                                                'accountcode': accountcode,
                                                'switch_id': switch_id,},
                                                {
                                                '$inc': {'calls': 1,
                                                         'duration': duration }
                                            },upsert=True)

                                        # Country report collection
                                        current_y_m_d_h_m = datetime.strptime(str(start_uepoch)[:16], "%Y-%m-%d %H:%M")
                                        CDR_COUNTRY_REPORT.update(
                                                {
                                                'start_uepoch': current_y_m_d_h_m,
                                                'country_id': country_id,
                                                'accountcode': accountcode,
                                                'switch_id': switch_id,},
                                                {
                                                '$inc': {'calls': 1,
                                                         'duration': duration }
                                            },upsert=True)

                                        cdr_record_count = cdr_record_count + 1
                                        msg =\
                                        _('%(cdr_record_count)s Cdr(s) are uploaded, out of %(total_rows)s row(s) !!')\
                                        % {'cdr_record_count': cdr_record_count,
                                           'total_rows': total_rows}
                                        success_import_list.append(row)
                                except:
                                    msg = _("Error : invalid value for import! Check import samples.")
                                    type_error_import_list.append(row)

                            except:
                                msg = _("Error : invalid value for import! Check import samples.")
                                type_error_import_list.append(row)
                else:
                    msg = _("Error : You selected to import several times the same column")
        else:
            form = CDR_FileImport(request.user)

        ctx = RequestContext(request, {
            'title': _('Import CDR'),
            'form': form,
            'opts': opts,
            'model_name': opts.object_name.lower(),
            'app_label': _('Switch'),
            'rdr': rdr,
            'msg': msg,
            'success_import_list': success_import_list,
            'error_import_list': error_import_list,
            'type_error_import_list': type_error_import_list,
            'CDR_FIELD_LIST': list(CDR_FIELD_LIST),
            'CDR_FIELD_LIST_NUM': list(CDR_FIELD_LIST_NUM),
            })
        template = 'admin/cdr/switch/import_cdr.html'
        return render_to_response(template, context_instance=ctx)

admin.site.register(Switch, SwitchAdmin)


# HangupCause
class HangupCauseAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'enumeration', 'cause', 'description')
    search_fields = ('code', 'enumeration',)

admin.site.register(HangupCause, HangupCauseAdmin)
