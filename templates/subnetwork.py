# Copyright 2018 Google Inc. All rights reserved.
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
""" This template creates a subnetwork. """


def generate_config(context):
    """ Entry point for the deployment resources. """

    subnetwork_resource = {
        'name': context.properties['name'],
        'type': 'gcp-types/compute-v1:subnetworks',
        'properties': {
            # Required properties.
            'network': context.properties['network'],
            'ipCidrRange': context.properties['ipCidrRange'],
            'region': context.properties['region'],
            'project': context.properties['projectId'],

            # Optional properties, with defaults.
            'enableFlowLogs': context.properties.get('enableFlowLogs', False),
            'privateIpGoogleAccess': context.properties.get(
                'privateIpGoogleAccess', False),
            'secondaryIpRanges': context.properties.get(
                'secondaryIpRanges', []),
        }
    }

    # Pass the 'dependsOn' property to the subnetwork resource if present.
    if 'dependsOn' in context.properties:
      subnetwork_resource['metadata'] = {
          'dependsOn': context.properties['dependsOn']
      }


    output = [
        {
            'name': 'name',
            'value': subnetwork_resource['name'],
        },
        {
            'name': 'selfLink',
            'value': '$(ref.{}.selfLink)'.format(subnetwork_resource['name']),
        },
    ]

    return {'resources': [subnetwork_resource], 'outputs': output}
