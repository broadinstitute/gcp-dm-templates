""" This template creates a Cloud DNS zone for Private Google Access"""

def generate_config(context):
  """ Entry point for the deployment resources. """

  zone_resource = {
      'name': context.properties['resourceName'],
      # https://cloud.google.com/dns/docs/reference/v1/managedZones
      'type': 'gcp-types/dns-v1:managedZones',
      'properties': {
          'name': 'Private Google APIs access',
          'description': 'Routes googleapis.com to restricted.googleapis.com VIP',
          'dnsName': 'googleapis.com',
          'project': context.properties['projectId'],
          'visibility': 'private',
          'privateVisibilityConfig': {
              'kind': 'dns#managedZonePrivateVisibilityConfigNetwork',
              'networks': [{
                  'kind': 'dns#managedZonePrivateVisibilityConfigNetwork',
                  'networkUrl': context.properties['networkUrl']
              }]
          }
      }
  }

  # If a dependsOn property was passed in, the network should depend on that.
  if 'dependsOn' in context.properties:
    zone_resource['metadata'] = {
        'dependsOn': context.properties['dependsOn']
    }

  return {'resources': [zone_resource]}
