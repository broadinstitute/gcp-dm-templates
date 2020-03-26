""" This template creates a Cloud DNS zone for Private Google Access"""

# Note: when updating this template, increment `private-google-access-version` in `firecloud_project.py`. This way, we
# can (1) track whether a project has been configured with private access, and (2) if we make any future changes to how
# this is configured, identify which projects were provisioned using this version of the template vs. a newer version.

def generate_config(context):
  """ Entry point for the deployment resources. """
  project = context.properties['projectId']
  zone_resource_name = context.properties['resourceName']

  resources = []

  zone_resource = {
    'name': zone_resource_name,
    # https://cloud.google.com/dns/docs/reference/v1/managedZones
    'type': 'gcp-types/dns-v1:managedZones',
    'properties': {
      'description': 'Routes googleapis.com to restricted.googleapis.com VIP',
      'dnsName': 'googleapis.com.',
      'project': project,
      'visibility': 'private',
      'privateVisibilityConfig': {
        'kind': 'dns#managedZonePrivateVisibilityConfig',
        'networks': [{
          'kind': 'dns#managedZonePrivateVisibilityConfigNetwork',
          'networkUrl': context.properties['network']
        }]
      }
    }
  }

  # If a dependsOn property was passed in, the network should depend on that.
  if 'dependsOn' in context.properties:
    zone_resource['metadata'] = {
      'dependsOn': context.properties['dependsOn']
    }
  resources.append(zone_resource)

  # Configure the DNS Zone. The two additions below will create Change records which will create ResourceRecordSets.
  # This follows the structure described here: https://cloud.google.com/vpc-service-controls/docs/set-up-private-connectivity#configuring-dns
  resources.append({
    'name': 'cname-record',
    # https://cloud.google.com/dns/docs/reference/v1/changes/create
    'action': 'gcp-types/dns-v1:dns.changes.create',
    'metadata': {
      'runtimePolicy': [
        'CREATE',
      ],
    },
    'properties': {
      'project': project,
      'managedZone': '$(ref.{}.name)'.format(zone_resource_name),
      'additions': [{
        'name': '*.googleapis.com.',
        'type': 'CNAME',
        'ttl': 300,
        'rrdatas': [ 'restricted.googleapis.com.' ]
      }]
    }
  })

  resources.append({
    'name': 'a-record',
    # https://cloud.google.com/dns/docs/reference/v1/changes/create
    'action': 'gcp-types/dns-v1:dns.changes.create',
    'metadata': {
      'runtimePolicy': [
        'CREATE',
      ],
    },
    'properties': {
      'project': project,
      'managedZone': '$(ref.{}.name)'.format(zone_resource_name),
      'additions': [{
        'name': 'restricted.googleapis.com.',
        'type': 'A',
        'ttl': 300,
        'rrdatas': [
          '199.36.153.4',
          '199.36.153.5',
          '199.36.153.6',
          '199.36.153.7'
        ]
      }]
    }
  })

  return {'resources': resources}
