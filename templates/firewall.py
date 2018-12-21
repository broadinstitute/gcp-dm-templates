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
""" This template creates firewall rules for a network. """


def generate_config(context):
    """ Entry point for the deployment resources. """
    resources = []

    for rule in context.properties.get('rules', []):
      # Network and project must be specified in the top-level properties.
      rule['network'] = context.properties['network']
      rule['project'] = context.properties['projectId']
      rule['priority'] = context.properties.get('priority', 65534)

      resource = {
          'name': rule['name'],
          'type': 'gcp-types/compute-v1:firewalls',
          'properties': rule,
      }
      resources.append(resource)

      # If a dependsOn property was passed in, the firewall should depends on
      # that.
      if 'dependsOn' in context.properties:
        resource['metadata'] = {
          'dependsOn': context.properties['dependsOn']
        }

    outputs = [{
        'name': 'resourceNames',
        'value': [resource['name'] for resource in resources]
    }]

    return {'resources': resources, 'outputs': outputs}
