""" This template creates a Cloud DNS zone for Private Google Access"""

def generate_config(context):
  """ Entry point for the deployment resources. """
  project = context.properties['projectId']
  zone_resource_name = context.properties['resourceName']
  network_url = "https://www.googleapis.com/compute/v1/projects/{project}/global/networks/{network}".format(project=project,network=context.properties['networkName'])

  resources = []

  zone_resource = {
      'name': zone_resource_name,
      # https://cloud.google.com/dns/docs/reference/v1/managedZones
      'type': 'gcp-types/dns-v1:managedZones',
      'properties': {
          # 'name': 'test-dns-name',
          'description': 'Routes googleapis.com to restricted.googleapis.com VIP',
          'dnsName': 'googleapis.com.',
          'project': project
          # 'visibility': 'private',
          # 'privateVisibilityConfig': {
          #     'kind': 'dns#managedZonePrivateVisibilityConfig',
          #     'networks': [{
          #         'kind': 'dns#managedZonePrivateVisibilityConfigNetwork',
          #         'networkUrl': 'network'
          #     }]
          # }
      }
  }

  # If a dependsOn property was passed in, the network should depend on that.
  if 'dependsOn' in context.properties:
    zone_resource['metadata'] = {
        'dependsOn': context.properties['dependsOn']
    }
  resources.append(zone_resource)



  dns_resource_record_set = {
      'name': 'dns-resource-record-set',
      # https://cloud.google.com/dns/docs/reference/v1/resourceRecordSets
      'type': 'gcp-types/dns-v1:resourceRecordSets',
      'properties': {
          'name': 'resource-record-set',
          'managedZone': '$(ref.{resource_name}.name)'.format(resource_name=zone_resource_name),
              #zone_resource['properties']['name'], #todo: not sure if this works
          #'$(ref.{resource_name}.name)'.format(resource_name=zone_resource['name']),
          'records': [{
                  'name': '*.googleapis.com.',
                  'type': 'CNAME',
                  'ttl': 300,
                  'rrdatas': [
                      'restricted.googleapis.com.'
                  ]
              },{
                  'name': 'restricted.googleapis.com.',
                  'type': 'A',
                  'ttl': 300,
                  'rrdatas': [
                      '199.36.153.4',
                      '199.36.153.5',
                      '199.36.153.6',
                      '199.36.153.7'
                  ]
              }
          ]
      }
  }
  resources.append(dns_resource_record_set)

  return {'resources': resources}
