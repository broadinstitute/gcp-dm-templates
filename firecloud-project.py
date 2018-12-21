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

FIREWALL_RESOURCE_NAME = 'fc-firewall'
PROJECT_RESOURCE_NAME = 'fc-project'
NETWORK_RESOURCE_NAME = 'fc-network'


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
      'name': 'fc-network',
      'properties': {
          'name': 'network',
          'projectId': '$(ref.fc-project.projectId)',
          'autoCreateSubnetworks': False,
          'subnetworks': subnetworks,
          # We pass the dependsOn list into the network template as a
          # parameter. Deployment Manager doesn't support dependsOn for
          # template-call nodes, so we can't have this resource itself depend on
          # the project-wide resources.
          'dependsOn': '$(ref.fc-project.resourceNames)',
      },
  }]


def create_firewall(context):
  """Creates a VPC firewall config."""
  return [{
      'type': 'templates/firewall.py',
      'name': 'fc-firewall',
      'properties': {
          'projectId': '$(ref.fc-project.projectId)',
          'network': '$(ref.fc-network.selfLink)',
          'dependsOn': '$(ref.fc-network.resourceNames)',
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
  }]

def create_iam_policies(context):
  """Creates a list of IAM policies for the new project."""
  organization_id = context.properties.get(
      'parentOrganization', FIRECLOUD_ORGANIZATION_ID)
  owners_and_viewers = [
      'group:{}'.format(context.properties['projectOwnersGroup']),
      'group:{}'.format(context.properties['projectViewersGroup']),
  ]
  owners_only = [
      'group:{}'.format(context.properties['projectOwnersGroup']),
  ]

  # TODO: handle the RequesterPays role (which has slightly different names in
  # different orgs) in an elegant way.
  #
  # Should look something like:
  # {
  #   # Owners & viewers are given the custom RequesterPays role to be able to
  #   # pay for their own GCS bucket access.
  #   'role': 'roles/{}/RequesterPays'.format(organization_id),
  #   'members': owners_and_viewers,
  # }

  # TODO: there's an issue with granting cross-org roles/owner permission, so we
  # can't currently assign roles/owner to the firecloud.org groups. This will be
  # an issue for BYOO so we may have to adjust these permissions.
  # {
  #   # FireCloud requires project owner permission to handle project
  #   # maintenance and ongoing updates to IAM configs.
  #   'role': 'roles/owner',
  #   'members': [
  #      'user:billing@firecloud.org',
  #      'group:firecloud-project-owners@firecloud.org'
  #  ]
  # }

  return [{
      # Rawls requires project editor permission to handle transactional IAM
      # updates to the project.
      #
      # Cromwell requires project editor permission because _____ ?
      'role': 'roles/editor',
      'members': [
          'serviceAccount:rawls-prod@broad-dsde-prod.iam.gserviceaccount.com',
          'serviceAccount:cromwell-prod@broad-dsde-prod.iam.gserviceaccount.com',
      ]
  }, {
      # Only FireCloud project owners are allowed to view the GCP project.
      'role': 'roles/viewer',
      'members': owners_only,
  }, {
      # Owners can manage billing on the GCP project (to switch out billing
      # accounts).
      'role': 'roles/billing.projectManager',
      'members': owners_only,
  }, {
      # Owners & viewers are allowed to spin up PAPI nodes in the
      # project (required for creating Leonardo notebooks).
      'role': 'roles/genomics.pipelinesRunner',
      'members': owners_and_viewers,
  }, {
      # Owners & viewers are allowed to run BigQuery queries in the project
      # (required for running BQ queries within notebooks).
      'role': 'roles/bigquery.jobUser',
      'members': owners_and_viewers,
  },
  ]

def create_pubsub_notification(context, depends_on, status_string):
  """Creates a resource to publish a message upon deployment completion.

  Arguments:
    context: the DM context object.
    depends_on: a list of resource names this notification should depend on.
    status_string: the "status" attribute value to publish, e.g. 'STARTED' or
      'COMPLETED'.

  Returns:
    A list of resource definitions.
  """

  return [{
      'name': 'pubsub-notification-{}'.format(status_string),
      'action': 'gcp-types/pubsub-v1:pubsub.projects.topics.publish',
      'properties': {
          'topic': context.properties['pubsubTopic'],
          'messages': [{
            'attributes': {
                'projectId': context.properties['projectId'],
                'status': status_string,
            }
          }]
      },
      'metadata': {
          # The notification should only run after *all* project-related
          # resources have been deployed.
          'dependsOn': depends_on,
          # Only trigger the pubsub message when the deployment is created (not on
          # update or delete).
          'runtimePolicy': ['UPDATE_ALWAYS'],
      },
  }]


def generate_config(context):
  """Entry point, called by deployment manager."""
  resources = []

  # Create an initial 'STARTED' pubsub notification.
  if 'pubsubTopic' in context.properties:
    resources.extend(create_pubsub_notification(
        context,
        depends_on=[],
        status_string='STARTED',
    ))

  # Required properties.
  billing_account_id = context.properties['billingAccountId']
  project_id = context.properties['projectId']

  # Optional properties, with defaults.
  high_security_network = context.properties.get('highSecurityNetwork', False)

  if 'parentFolder' in context.properties:
    parent_obj = {
        'id': context.properties['parentFolder'],
        'type': 'folder'
    }
  elif 'parentOrganization' in context.properties:
    parent_obj = {
        'id': context.properties['parentOrganization'],
        'type': 'organization'
    }
  else:
    parent_obj = {
        'id': FIRECLOUD_ORGANIZATION_ID,
        'type': 'organization',
    }

  # Use a project name if given, otherwise it's safe to fallback to use the
  # project ID as the name.
  project_name = context.properties.get('projectName', project_id)
  labels_obj = context.properties.get('labels', {})

  # Create the main project resource.
  resources.append({
      'type': 'templates/project.py',
      'name': 'fc-project',
      'properties': {
          'activateApis': FIRECLOUD_REQUIRED_APIS,
          'billingAccountId': billing_account_id,
          'iamPolicies': create_iam_policies(context),
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
    resources.extend(create_network(context))
    resources.extend(create_firewall(context))

  if 'pubsubTopic' in context.properties:
    resources.extend(create_pubsub_notification(
        context,
        # This is somewhat hacky, but we can't simply collect the name of each
        # collected resource since template call nodes aren't "real" resources
        # that can be part of a dependsOn stanza. So instead, we collect the
        # names of all resources that are output by the network (which itself
        # depends on the project). It doesn't seem to be possible to concatenate
        # dependsOn arrays within the reference syntax, otherwise we could make
        # this depend explicitly on all resources from the template nodes.
        depends_on= '$(ref.fc-network.resourceNames)',
        status_string='COMPLETED'
    ))

  return {'resources': resources}
