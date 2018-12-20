"""A top-level template which creates a FireCloud GCP project.

This is meant to be used as a composite type using the GCP Cloud Deployment
Manager. See the .py.schema file for more details on how to use the composite
type.
"""

FIRECLOUD_NETWORK_REGIONS = {
    'us-central1': '10.128.0.0/20',
    'us-east1': '10.130.0.0/20',
    'us-east4': '10.132.0.0/20',
}
# For testing, this is the organization ID for verily-bvdp.com
FIRECLOUD_ORGANIZATION_ID = '336383161826'
FIRECLOUD_REQUIRED_APIS = [
    'bigquery-json.googleapis.com',
    'clouddebugger.googleapis.com',
    'compute.googleapis.com',
    'container.googleapis.com',
    'containerregistry.googleapis.com',
    'dataflow.googleapis.com',
    'dataproc.googleapis.com',
    'deploymentmanager.googleapis.com',
    'genomics.googleapis.com',
    'logging.googleapis.com',
    'monitoring.googleapis.com',
    'pubsub.googleapis.com',
    'replicapool.googleapis.com',
    'replicapoolupdater.googleapis.com',
    'resourceviews.googleapis.com',
    'sql-component.googleapis.com',
    'storage-api.googleapis.com',
    'storage-component.googleapis.com',
]

FIREWALL_RESOURCE_NAME = 'firewall'
PROJECT_RESOURCE_NAME = 'project'
NETWORK_RESOURCE_NAME = 'network'


def create_network(context):
  """Creates a VPC network resource config."""
  subnetworks = []
  for region in FIRECLOUD_NETWORK_REGIONS:
    subnetworks.append({
        'name': 'fc-{}'.format(region),
        'region': region,
        'ipCidrRange': FIRECLOUD_NETWORK_REGIONS[region],
        'enableFlowLogs': True,
    })

  return [{
      'type': 'templates/network.py',
      'name': NETWORK_RESOURCE_NAME,
      'properties': {
          'autoCreateSubnetworks': False,
          'subnetworks': subnetworks,
      },
      'metadata': {
          'dependsOn': [PROJECT_RESOURCE_NAME],
      }
  }]


def create_firewall(context):
  """Creates a VPC firewall config."""
  return {
      'type': 'templates/firewall.py',
      'name': FIREWALL_RESOURCE_NAME,
      'properties': {
          # This deployment manager reference string allows us to connect the
          # firewall to the network, via the selfLink URL once it exists.
          'network': '$(ref.{}.selfLink)'.format(NETWORK_RESOURCE_NAME),
          'rules': [{
              'name': 'allow-icmp',
              'description': 'Allow ICMP from anywhere.',
              'allowed': [{
                  'IPProtocol': 'icmp'
              }],
              'direction': 'INGRESS',
              'sourceRanges': ['0.0.0.0/0'],
              'priority': 65534,
          }, {
              'name': 'allow-internal',
              'description': 'Allow internal traffic on the network.',
              'allowed': [{
                  'IPProtocol': 'icmp',
              }, {
                  'IPProtocol': 'tcp',
                  'ports': ['0-65535'],
              }, {
                  'IPProtocol': 'udp',
                  'ports': ['0-65535'],
              }],
              'direction': 'INGRESS',
              'sourceRanges': ['10.128.0.0/9'],
              'priority': 65534,
          }, {
              'name': 'leonardo-ssl',
              'description': 'Allow SSL traffic from Leonardo-managed VMs.',
              'allowed': [{
                  'IPProtocol': 'tcp',
                  'ports': ['443'],
              }],
              'direction': 'INGRESS',
              'sourceRanges': ['0.0.0.0/0'],
              'targetTags': ['leonardo'],
          }],
      },
      'metadata': {
          'dependsOn': [NETWORK_RESOURCE_NAME],
      }
  }

def GenerateConfig(context):
  """Entry point, called by deployment manager."""
  resources = []

  # Required properties.
  billing_account_id = context.properties['billingAccountId']
  project_id = context.properties['projectId']

  # Optional properties, with defaults.
  high_security_network = context.properties.get('highSecurityNetwork', False)
  parent_obj = context.properties.get('parent', {
      'id': FIRECLOUD_ORGANIZATION_ID,
      'type': 'organization',
  })
  project_name = context.properties.get('projectName', project_id)
  labels_obj = context.properties.get('labels', {})

  # Create the main project resource.
  resources.append({
      'type': 'templates/project.py',
      'name': PROJECT_RESOURCE_NAME,
      'properties': {
          'activateApis': FIRECLOUD_REQUIRED_APIS,
          'billingAccountId': billing_account_id,
          # This causes APIs to be activated in parallel rather than serially. This
          # dramatically speeds up the process, but may run into quota issues if too
          # many projects are activated at the same time.
          'concurrentApiActivation': False,
          'labels': labels_obj,
          'name': project_name,
          # The project parent. For FireCloud, this should refer to the
          # firecloud.org (or equivalent) GCP organization ID. For BYOO
          # projects, this might refer to an external organization or folder ID.
          'parent': parent_obj,
          # If true, this would remove the default compute egine service
          # account. FireCloud doesn't use this SA, but we're leaving this set
          # to False to avoid changing any legacy behavior, at least initially.
          'projectId': project_id,
          'removeDefaultSA': False,
          # Removes the default VPC network for projects requiring stringent
          # network security configurations.
          'removeDefaultVPC': True if high_security_network else False,
          # Always set up a usage bucket export for FireCloud.
          'usageExportBucket': True
      }
  })

  if high_security_network:
    resources.append(create_network(context))
    resources.append(create_firewall(context))

  return {'resources': resources}
