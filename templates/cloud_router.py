# Based on https://github.com/GoogleCloudPlatform/cloud-foundation-toolkit/tree/v0.3.5/dm/templates/cloud_router
# Original Copyright 2018 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" This template creates a Cloud Router. """


def append_optional_property(res, properties, prop_name):
    """ If the property is set, it is added to the resource. """

    val = properties.get(prop_name)
    if val:
        res['properties'][prop_name] = val
    return

def generate_config(context):
    """ Entry point for the deployment resources. """

    resource_name = context.properties['resourceName']

    properties = context.properties

    router = {
        'name': resource_name,
        # https://cloud.google.com/compute/docs/reference/rest/v1/routers
        'type': 'gcp-types/compute-v1:routers',
        'properties':
            {
                'name':
                    properties['name'],
                'project':
                    properties['projectId'],
                'region':
                    properties['region'],
                'network':
                    properties['network'],
            }
    }

    # If a dependsOn property was passed in, the router should depend on that.
    if 'dependsOn' in context.properties:
        router['metadata'] = {
            'dependsOn': context.properties['dependsOn']
        }

    optional_properties = [
        'description',
        'nats',
    ]

    for prop in optional_properties:
        append_optional_property(router, properties, prop)

    return {'resources': [router]}
