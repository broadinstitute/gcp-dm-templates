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
""" This template creates a network, optionally with subnetworks. """


def generate_config(context):
  """ Entry point for the deployment resources. """

  resource_name = context.properties['resourceName']
  network_self_link = '$(ref.{}.selfLink)'.format(resource_name)

  resources = []

  network_resource = {
      'name': resource_name,
      'type': 'gcp-types/compute-v1:networks',
      'properties': {
          'name':
              context.properties['name'],
          'project':
              context.properties['projectId'],
          'autoCreateSubnetworks':
              context.properties.get('autoCreateSubnetworks', False),
      },
  }
  resources.append(network_resource)

  # If a dependsOn property was passed in, the network should depend on that.
  if 'dependsOn' in context.properties:
    network_resource['metadata'] = {
        'dependsOn': context.properties['dependsOn']
    }

  # Create the network within a specified project if the property is
  # non-empty.
  if 'projectId' in context.properties:
    network_resource['properties']['project'] = (
        context.properties['projectId'])

  for subnetwork in context.properties.get('subnetworks', []):
    subnetwork['network'] = network_self_link

    # All subnetworks  depend on the parent network resource.
    subnetwork['dependsOn'] = [resource_name]

    # Create the subnetwork within the specified project if the property is
    # non-empty.
    if 'projectId' in context.properties:
      subnetwork['projectId'] = context.properties['projectId']

    resources.append({
        'name': subnetwork['resourceName'],
        'type': 'subnetwork.py',
        'properties': subnetwork
    })

    # todo: this is the step 2 that we skipped in manual testing ; try it out
  if context.properties.get('createCustomStaticRoute', False):
      resources.append({
          'name': 'private-google-access-route',
          # https://cloud.google.com/compute/docs/reference/rest/v1/routes
          'type': 'gcp-types/compute-v1:routes',
          'properties': {
              'name': 'private-google-access-route',
              'network': '$(ref.{resource_name}.name)'.format(resource_name=resource_name),
              'destRange': '199.36.153.4/30',
              'nextHopGateway': 'default-internet-gateway'
          }
      })

  return {
      'resources':
          resources,
      'outputs': [{
          'name': 'name',
          'value': resource_name
      }, {
          'name': 'selfLink',
          'value': network_self_link
      },
                  {
                      'name': 'resourceNames',
                      'value': [resource['name'] for resource in resources]
                  }]
  }
