"""A top-level template which creates a FireCloud GCP project.

This is meant to be used as a composite type using the GCP Cloud Deployment
Manager. See the .py.schema file for more details on how to use the composite
type.


Template Version History
  Instructions:
    When updating DM templates, update the FIRECLOUD_PROJECT_TEMPLATE_VERSION_ID for any major feature change and add
    summarizing notes below.
  Version ID notes:
    1:
      Initial DM template(s), including all changes made prior to March 2020. Includes parameters for high-security
      networks and VPC flow logs in support of AoU security needs. This version number is not included in project
      metadata / labels. The absence of a number on a project should be implied to be this version.
    2:
      Added a privateIpGoogleAccess parameter, which fixes an issue where GCS bucket traffic could not be easily
      distinguished from internet egress. Started tracking template version numbers in project labels.
"""
import re

FIRECLOUD_PROJECT_TEMPLATE_VERSION_ID = '2'

GCP_REGIONS = ['asia-east1',
               'asia-east2',
               'asia-northeast1',
               'asia-northeast2',
               'asia-south1',
               'asia-southeast1',
               'australia-southeast1',
               'europe-north1',
               'europe-west1',
               'europe-west2',
               'europe-west3',
               'europe-west4',
               'europe-west6',
               'northamerica-northeast1',
               'southamerica-east1',
               'us-central1',
               'us-east1',
               'us-east4',
               'us-west1',
               'us-west2']

# The subnet ranges are expanded from the default 4,096 IP addresses (/20) to 65,536 IP addresses (/16) per region.
#
# One can expand the IP ranges later. FYI there is NOT an equivalent `shrink-ip-range`, only
# https://cloud.google.com/sdk/gcloud/reference/compute/networks/subnets/expand-ip-range
#
# /16 currently gives each region its own unique two-octal subnet.
#
# NOTE: As of 2021-06-30 the IP ranges here have drifted from the list in RBS.
# The two repositories contain a different set of regions, and the regions have been assigned different subnets.
# https://github.com/DataBiosphere/terra-resource-buffer/blob/42815268a8c18d37d582db92f73db717ce5a4d5f/src/main/java/bio/terra/buffer/service/resource/flight/CreateSubnetsStep.java
def iprange(number):
  return '10.' + str(number) + '.0.0/16'

#assign IP ranges programmatically, because typing them out terrifies me
FIRECLOUD_NETWORK_REGIONS = { region: iprange(128 + 2*i) for (i, region) in enumerate(GCP_REGIONS) }

FIRECLOUD_REQUIRED_APIS = [
  "bigquery-json.googleapis.com",
  "compute.googleapis.com",
  "container.googleapis.com",
  "cloudbilling.googleapis.com",
  "clouderrorreporting.googleapis.com",
  "cloudkms.googleapis.com",
  "cloudtrace.googleapis.com",
  "containerregistry.googleapis.com",
  "dataflow.googleapis.com",
  "dataproc.googleapis.com",
  "genomics.googleapis.com",
  "lifesciences.googleapis.com",
  "logging.googleapis.com",
  "monitoring.googleapis.com",
  "storage-api.googleapis.com",
  "storage-component.googleapis.com",
  "dns.googleapis.com"
]

FIRECLOUD_VPC_NETWORK_NAME = "network"
FIRECLOUD_VPC_SUBNETWORK_NAME = "subnetwork"

def create_default_network(context):
  """Creates a default VPC network resource.

  Args:
      context: the DM context object.

  Returns:
      A resource instantiating the network.py sub-template.
  """
  return [{
    'type': 'templates/network.py',
    'name': 'fc-network',
    'properties': {
      'resourceName': 'network',
      'name': 'network',
      'projectId': '$(ref.fc-project.projectId)',
      'autoCreateSubnetworks': True,
      # We pass the dependsOn list into the network template as a
      # parameter. Deployment Manager doesn't support dependsOn for
      # template-call nodes, so we can't have this resource itself depend on
      # the project-wide resources.
      'dependsOn': '$(ref.fc-project.resourceNames)',
    },
  }]


def create_high_security_network(context):
  """Creates a high-security VPC network resource.

  Args:
      context: the DM context object.

  Returns:
      A resource instantiating the network.py sub-template.
  """
  subnetworks = []
  private_ip_google_access = context.properties.get('privateIpGoogleAccess', False)
  for region in FIRECLOUD_NETWORK_REGIONS:
    subnetworks.append({
      # We append the region to the subnetwork's DM resource name, since
      # each resource name needs to be globally unique within the deployment.
      'resourceName': FIRECLOUD_VPC_SUBNETWORK_NAME + '_' + region,
      # We want all subnetworks to have the same object name, since this most
      # closely mirrors how auto-mode subnets work and is what PAPI expects.
      'name': FIRECLOUD_VPC_SUBNETWORK_NAME,
      'region': region,
      'ipCidrRange': FIRECLOUD_NETWORK_REGIONS[region],
      'enableFlowLogs': context.properties.get('enableFlowLogs', False),
      'privateIpGoogleAccess': private_ip_google_access
    })

  return [{
    'type': 'templates/network.py',
    'name': 'fc-network',
    'properties': {
      'resourceName': 'network',
      'name': FIRECLOUD_VPC_NETWORK_NAME,
      'projectId': '$(ref.fc-project.projectId)',
      'autoCreateSubnetworks': False,
      'subnetworks': subnetworks,
      # We pass the dependsOn list into the network template as a
      # parameter. Deployment Manager doesn't support dependsOn for
      # template-call nodes, so we can't have this resource itself depend on
      # the project-wide resources.
      'dependsOn': '$(ref.fc-project.resourceNames)',
      'createCustomStaticRoute': private_ip_google_access
    },
  }]

def create_private_google_access_dns_zone(context):
  """Creates a DNS Zone for the use of Private Google Access

  The DNS Zone config depends on the VPC network having been completely
  instantiated, so it includes a dependsOn reference to the list of resources
  generated by the network sub-template.

  Args:
    context: the DM context object.

  Returns:
    A resource instantiating the private_google_access_dns_zone.py sub-template.
  """
  return [{
    'type': 'templates/private_google_access_dns_zone.py',
    'name': 'fc-private-google-access-dns-zone',
    'properties': {
      'resourceName': 'private-google-access-dns-zone',
      'projectId': '$(ref.fc-project.projectId)',
      'network': '$(ref.fc-network.selfLink)',
      'dependsOn': '$(ref.fc-network.resourceNames)'
    }
  }]


def create_firewall(context):
  """Creates a VPC firewall config.

  The VPC firewall config depends on the VPC network having been completely
  instantiated, so it includes a dependsOn reference to the list of resources
  generated by the network sub-template.

  Args:
      context: the DM context object.

  Returns:
      A resource instantiating the firewall.py sub-template.
  """
  return [{
    'type': 'templates/firewall.py',
    'name': 'fc-firewall',
    'properties': {
      'projectId':
        '$(ref.fc-project.projectId)',
      'network':
        '$(ref.fc-network.selfLink)',
      'dependsOn':
        '$(ref.fc-network.resourceNames)',
      'rules': [
        {
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
        },
        {
          'name': 'leonardo-ssl',
          'description': 'Allow SSL traffic from Leonardo-managed VMs.',
          'allowed': [{
            'IPProtocol': 'tcp',
            'ports': ['443'],
          }],
          'direction': 'INGRESS',
          'sourceRanges': ['0.0.0.0/0'],
          'targetTags': ['leonardo'],
        },
      ],
    },
  }]


def create_iam_policies(context):
  """Creates a list of IAM policies for the new project.

  Arguments:
      context: the DM context object.

  Returns:
      A list of policy resource definitions.
  """
  policies = []

  # First, we pre-fill the policy list with Firecloud-wide role grants. These
  # include roles given to the Rawls / Cromwell service accounts, as well as the
  # global Firecloud project owners group (used for administration / maintenance
  # by Firecloud devops).
  fc_project_editors = []
  fc_project_owners = []

  if 'fcBillingGroup' in context.properties:
    fc_project_owners.append('group:{}'.format(
      context.properties['fcBillingGroup']))

  if 'fcProjectEditors' in context.properties:
    fc_project_editors.extend(context.properties['fcProjectEditors'])

  if 'fcProjectOwners' in context.properties:
    fc_project_owners.extend(context.properties['fcProjectOwners'])

  if fc_project_editors:
    policies.append({
      'role': 'roles/editor',
      'members': fc_project_editors,
    })

  if fc_project_owners:
    policies.append({
      'role': 'roles/owner',
      'members': fc_project_owners,
    })

  # Now we handle granting IAM permissions that apply to Firecloud-managed
  # owners and viewers. We generally expect the 'projectOwnersGroup' and
  # 'projectViewersGroup' to be non-empty, but this code handles an empty value
  # for either in case that changes in the future.
  #
  # This list is populated with both the FC project OWNERS proxy group and the
  # FC project VIEWERS proxy group.
  owners_and_viewers = []
  # This list will contain the OWNERS proxy group only.
  owners_only = []

  if 'projectOwnersGroup' in context.properties:
    owners_and_viewers.append('group:{}'.format(
      context.properties['projectOwnersGroup']))
    owners_only.append('group:{}'.format(
      context.properties['projectOwnersGroup']))

  if 'projectViewersGroup' in context.properties:
    owners_and_viewers.append('group:{}'.format(
      context.properties['projectViewersGroup']))

  if owners_only:
    policies.extend([
      {
        # Only FireCloud project owners are allowed to view the GCP project.
        'role': 'roles/viewer',
        'members': owners_only,
      },
      {
        # Owners can manage billing on the GCP project (to switch out
        # billing accounts).
        'role': 'roles/billing.projectManager',
        'members': owners_only,
      },
    ])

  if owners_and_viewers:
    policies.extend([
      {
        # Owners & viewers are allowed to run BigQuery queries in the
        # project (required for running BQ queries within notebooks).
        'role': 'roles/bigquery.jobUser',
        'members': owners_and_viewers,
      },
      {
        # Owners & viewers are allowed to write logs in the
        # project (required for gathering logs for user VMs).
        'role': 'roles/logging.logWriter',
        'members': owners_and_viewers,
      },
      {
        # Owners & viewers are allowed to write metrics in the
        # project (required for gathering metrics for user VMs).
        'role': 'roles/monitoring.metricWriter',
        'members': owners_and_viewers,
      }
    ])

  # The requester pays role is an organization-wide role ID that should be
  # granted to both project owners and viewers.
  if 'requesterPaysRole' in context.properties and owners_and_viewers:
    policies.append({
      'role': context.properties['requesterPaysRole'],
      'members': owners_and_viewers,
    })

  return policies


def create_pubsub_notification(context, depends_on, status_string):
  """Creates a resource to publish a message upon deployment completion.

  Arguments:
      context: the DM context object.
      depends_on: a list of resource names this notification should depend on.
      status_string: the "status" attribute value to publish, e.g. 'STARTED' or
        'COMPLETED'.

  Returns:
    A list of pubsub Deployment Manager actions.
  """

  return [{
    'name': 'pubsub-notification-{}'.format(status_string),
    'action': 'gcp-types/pubsub-v1:pubsub.projects.topics.publish',
    'properties': {
      'topic':
        context.properties['pubsubTopic'],
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


def satisfy_label_requirements(k, v):
  """Takes in a key and value and returns (String, String) that satisfies the label text requirements.

  Label text requirements include max length of 63 chars, only allowing (a-z, 0-9, -, _),
  key must start with a letter, and value must be a string.
  https://cloud.google.com/deployment-manager/docs/creating-managing-labels#requirements

  Arguments:
    k: stringify-able input
    v: stringify-able input

  Returns:
    (String, String) that satisfies the label text requirements for key and value
  """

  LABEL_MAX_LENGTH = 63
  ALLOWED_CHARS_COMPLEMENT = r'[^a-z0-9-_]+'
  KEY_ALLOWED_STARTING_CHARS_COMPLEMENT = r'^[^a-z]*'

  new_k = str(k).lower()
  new_k = re.sub(KEY_ALLOWED_STARTING_CHARS_COMPLEMENT, '', new_k) # make sure first char of key is a lowercase letter
  new_k = re.sub(ALLOWED_CHARS_COMPLEMENT, '--', new_k) # remove each group of illegal characters and replace with '--'
  new_k = new_k[0:LABEL_MAX_LENGTH]

  new_v = str(v).lower()
  new_v = re.sub(ALLOWED_CHARS_COMPLEMENT, '--', new_v) # remove each group of illegal characters and replace with '--'
  new_v = new_v[0:LABEL_MAX_LENGTH]

  return new_k, new_v


def generate_config(context):
  """Entry point, called by deployment manager.

  Args:
      context: the Deployment Manager context object.

  Returns:
      A list of resources to be consumed by the Deployment Manager.
  """
  resources = []

  # Create an initial 'STARTED' pubsub notification.
  if 'pubsubTopic' in context.properties:
    resources.extend(
      create_pubsub_notification(
        context,
        depends_on=[],
        status_string='STARTED',
      ))

  # Required properties.
  billing_account_id = context.properties['billingAccountId']
  parent_organization = context.properties['parentOrganization']
  project_id = context.properties['projectId']

  # Optional properties, with defaults.
  high_security_network = context.properties.get('highSecurityNetwork', False)
  private_ip_google_access = context.properties.get('privateIpGoogleAccess', False)
  storage_bucket_lifecycle = context.properties.get('storageBucketLifecycle', 180)
  billing_account_friendly_name = context.properties.get('billingAccountFriendlyName', billing_account_id)
  # Use a project name if given, otherwise it's safe to fallback to use the
  # project ID as the name.
  project_name = context.properties.get('projectName', project_id)
  labels_obj = context.properties.get('labels', {})

  # Save this template's version number and all parameters inputs to the project metadata to keep track of what
  # operations were performed on a project.
  labels_obj.update({
    "firecloud-project-template-version" : str(FIRECLOUD_PROJECT_TEMPLATE_VERSION_ID)
  })

  for k, v in context.properties.items():
    label_k, label_v = satisfy_label_requirements('param--' + str(k), v)
    labels_obj.update({
      label_k: label_v
    })


  if high_security_network:
    labels_obj.update({
      "vpc-network-name" : FIRECLOUD_VPC_NETWORK_NAME,
      "vpc-subnetwork-name" : FIRECLOUD_VPC_SUBNETWORK_NAME
    })

  if 'parentFolder' in context.properties:
    parent_obj = {
      'id': context.properties['parentFolder'],
      'type': 'folder',
    }
  else:
    parent_obj = {
      'id': context.properties['parentOrganization'],
      'type': 'organization',
    }

  # Create the main project resource.
  resources.append({
    'type': 'templates/project.py',
    'name': 'fc-project',
    'properties': {
      'activateApis': FIRECLOUD_REQUIRED_APIS,
      'billingAccountId': billing_account_id,
      'billingAccountFriendlyName': billing_account_friendly_name,
      'iamPolicies': create_iam_policies(context),
      'labels': labels_obj,
      'name': project_name,
      # The project parent. For FireCloud, this should refer to the
      # firecloud.org (or equivalent) GCP organization ID.
      'parent': parent_obj,
      'projectId': project_id,
      # If true, this would remove the default compute egine service
      # account. FireCloud doesn't use this SA, but we're leaving this set
      # to False to avoid changing any legacy behavior, at least initially.
      'removeDefaultSA': False,
      # Removes the default VPC network for projects requiring stringent
      # network security configurations.
      'removeDefaultVPC': high_security_network,
      'createUsageExportBucket': False,
      # Always set up the storage logs and cromwell auth buckets for Firecloud
      'storageLogsBucket': True,
      'storageBucketLifecycle': storage_bucket_lifecycle,
      'cromwellAuthBucket': True
    }
  })

  if high_security_network:
    resources.extend(create_high_security_network(context))
    resources.extend(create_firewall(context))
    if private_ip_google_access:
      resources.extend(create_private_google_access_dns_zone(context))
  else:
    resources.extend(create_default_network(context))

  if 'pubsubTopic' in context.properties:
    resources.extend(
      create_pubsub_notification(
        context,
        # This is somewhat hacky, but we can't simply collect the name of each
        # collected resource since template call nodes aren't "real" resources
        # that can be part of a dependsOn stanza. So instead, we collect the
        # names of all resources that are output by the network (which itself
        # depends on the project). It doesn't seem to be possible to concatenate
        # dependsOn arrays within the reference syntax, otherwise we could make
        # this depend explicitly on all resources from the template nodes.
        depends_on='$(ref.fc-network.resourceNames)',
        status_string='COMPLETED'))

  return {'resources': resources}
