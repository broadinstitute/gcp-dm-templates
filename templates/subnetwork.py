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

  enable_flow_logs = context.properties.get('enableFlowLogs', False)

  subnetwork_resource = {
      'name': context.properties['resourceName'],
      'type': 'gcp-types/compute-beta:subnetworks',
      'properties': {
          # Required properties.
          'name':
              context.properties['name'],
          'network':
              context.properties['network'],
          'ipCidrRange':
              context.properties['ipCidrRange'],
          'region':
              context.properties['region'],
          'project':
              context.properties['projectId'],

          # Optional properties, with defaults.
          'enableFlowLogs':
              enable_flow_logs,
          'privateIpGoogleAccess':
              context.properties.get('privateIpGoogleAccess', False),
          'secondaryIpRanges':
              context.properties.get('secondaryIpRanges', []),
      }
  }
  
  if enable_flow_logs:
    # If flow logs are enabled, we want to adjust the default config in two ways:
    # (1) Increase the sampling ratio (defaults to 0.5) so we sample all traffic.
    # (2) Reduce the aggregation interval to 30 seconds (default is 5secs) to save on
    #     storage.
    subnetwork_resource['properties']['logConfig'] = {
        'aggregationInterval': 'INTERVAL_30_SEC',
        'enable': True,
        'flowSampling': 1.0,
        'metadata': 'INCLUDE_ALL_METADATA',
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
