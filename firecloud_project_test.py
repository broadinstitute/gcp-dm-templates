import unittest

import firecloud_project


class FakeContext(object):

  def __init__(self):
    self.env = {}
    self.properties = {}


def resource_with_name(resources, name):
  """Returns the resource with the given name."""
  matches = [x for x in resources if x['name'] == name]
  if matches:
    return matches[0]
  else:
    raise Exception('No resource matching name {}'.format(name))


def policy_with_role(policies, role):
  """Returns the policy with the given name."""
  matches = [x for x in policies if x['role'] == role]
  if matches:
    return matches[0]
  else:
    raise Exception('No policy matching role {}'.format(role))


class FirecloudProjectTest(unittest.TestCase):

  def setUp(self):
    self.context = FakeContext()
    self.context.properties.update({
        # These are the required properties for the FC project template.
        'billingAccountId': '111-111',
        'parentOrganization': '12345',
        'projectId': 'my-project',
    })

  def test_only_required_params(self):
    """Basic test case, checking top-level resources created."""
    result = firecloud_project.generate_config(self.context)
    self.assertIsNotNone(result['resources'])
    resources = result['resources']

    # The project-level resource is named fc-project and calls out to the
    # project.py template.
    project = resource_with_name(resources, 'fc-project')

    self.assertEqual(project['type'], 'templates/project.py')
    self.assertEqual(project['properties']['billingAccountId'], '111-111')
    self.assertEqual(project['properties']['name'], 'my-project')
    self.assertEqual(project['properties']['activateApis'],
                     firecloud_project.FIRECLOUD_REQUIRED_APIS)

    # The 'parent' param sent to the project.py template should refer to the
    # organization ID.
    self.assertEqual(project['properties']['parent'], {
        'id': '12345',
        'type': 'organization'
    })

    # A default network resource is created.
    network = resource_with_name(resources, 'fc-network')
    self.assertEqual(network['type'], 'templates/network.py')
    self.assertTrue(network['properties']['autoCreateSubnetworks'])

  def test_parent_folder(self):
    """Verifies behavior when a GCP folder is specified as parent."""
    self.context.properties['parentFolder'] = '99999'
    resources = firecloud_project.generate_config(self.context)['resources']
    project = resource_with_name(resources, 'fc-project')
    self.assertEqual(project['properties']['parent'], {
        'id': '99999',
        'type': 'folder'
    })

  def test_secure_network(self):
    """Verifying changes made with the high-security network option."""
    self.context.properties['highSecurityNetwork'] = True
    resources = firecloud_project.generate_config(self.context)['resources']

    project = resource_with_name(resources, 'fc-project')
    self.assertTrue(project['properties']['removeDefaultVPC'])

    # The network sub-template is called, with autoCreate turned off and a
    # specific set of subnetworks specified.
    network = resource_with_name(resources, 'fc-network')
    self.assertFalse(network['properties']['autoCreateSubnetworks'])
    subregion_count = len(firecloud_project.FIRECLOUD_NETWORK_REGIONS.keys())
    self.assertEqual(len(network['properties']['subnetworks']), subregion_count)

    # A custom firewall resource is created with a set of expected rules.
    firewall = resource_with_name(resources, 'fc-firewall')
    self.assertEqual([x['name'] for x in firewall['properties']['rules']],
                     ['allow-icmp', 'allow-internal', 'leonardo-ssl'])

  def test_iam_policies(self):
    """Tests that IAM grants are correctly generated for FC owners & groups."""
    props = self.context.properties
    props['fcCromwellServiceAccount'] = 'cromwell@firecloud.org'
    props['fcRawlsServiceAccount'] = 'rawls@firecloud.org'
    props['fcBillingGroup'] = 'terra-billing@firecloud.org'
    props['fcProjectOwnersGroup'] = 'project-owners@firecloud.org'

    props['projectOwnersGroup'] = 'proxy-group-owners@firecloud.org'
    props['projectViewersGroup'] = 'proxy-group-viewers@firecloud.org'
    props['requesterPaysRole'] = 'roles/1234/RequesterPays'

    policies = firecloud_project.create_iam_policies(self.context)

    # Verify firecloud-wide IAM grants.
    self.assertEqual(
        policy_with_role(policies, 'roles/editor'), {
            'role':
                'roles/editor',
            'members': [
                'serviceAccount:rawls@firecloud.org',
                'serviceAccount:cromwell@firecloud.org'
            ]
        })

    self.assertEqual(
        policy_with_role(policies, 'roles/owner'), {
            'role':
                'roles/owner',
            'members': [
                'user:billing@firecloud.org',
                'group:project-owners@firecloud.org'
            ]
        })

    # Verify project-specific IAM grants.
    self.assertEqual(
        policy_with_role(policies, 'roles/viewer'), {
            'role': 'roles/viewer',
            'members': ['group:proxy-group-owners@firecloud.org']
        })
    self.assertEqual(
        policy_with_role(policies, 'roles/billing.projectManager'), {
            'role': 'roles/billing.projectManager',
            'members': ['group:proxy-group-owners@firecloud.org']
        })
    self.assertEqual(
        policy_with_role(policies, 'roles/genomics.pipelinesRunner'), {
            'role':
                'roles/genomics.pipelinesRunner',
            'members': [
                'group:proxy-group-owners@firecloud.org',
                'group:proxy-group-viewers@firecloud.org'
            ]
        })
    self.assertEqual(
        policy_with_role(policies, 'roles/bigquery.jobUser'), {
            'role':
                'roles/bigquery.jobUser',
            'members': [
                'group:proxy-group-owners@firecloud.org',
                'group:proxy-group-viewers@firecloud.org'
            ]
        })

    self.assertEqual(
        policy_with_role(policies, 'roles/1234/RequesterPays'), {
            'role':
                'roles/1234/RequesterPays',
            'members': [
                'group:proxy-group-owners@firecloud.org',
                'group:proxy-group-viewers@firecloud.org'
            ]
        })

  def test_pubsub_notifications(self):
    """Tests the creation of Pubsub notification resources."""
    self.context.properties[
        'pubsubTopic'] = 'projects/my-project/topics/deployments'
    resources = firecloud_project.generate_config(self.context)['resources']

    started = resource_with_name(resources, 'pubsub-notification-STARTED')
    self.assertEqual(started['properties']['topic'],
                     'projects/my-project/topics/deployments')
    started_attrs = started['properties']['messages'][0]['attributes']
    self.assertEqual(started_attrs['projectId'], 'my-project')
    self.assertEqual(started_attrs['status'], 'STARTED')

    completed = resource_with_name(resources, 'pubsub-notification-COMPLETED')
    completed_attrs = completed['properties']['messages'][0]['attributes']
    self.assertEqual(completed_attrs['status'], 'COMPLETED')
    # Ensure the COMPLETED message depends on the fc-network resources having
    # been finished. See comment in the .py file for details on how & why we do
    # this.
    self.assertEqual(completed['metadata']['dependsOn'],
                     '$(ref.fc-network.resourceNames)')


if __name__ == '__main__':
  unittest.main()