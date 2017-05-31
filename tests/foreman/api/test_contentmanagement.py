"""Test class for the content management tests.

@Requirement: Content Management

@CaseAutomation: Automated

@CaseLevel: Acceptance

@CaseComponent: API

@TestType: Functional

@CaseImportance: High

@Upstream: No
"""
import os

from fauxfactory import gen_string
from nailgun import entities
from robottelo import ssh
from robottelo.api.utils import promote
from robottelo.config import settings
from robottelo.constants import (
    DISTRO_RHEL7,
    FAKE_1_YUM_REPO,
    FAKE_1_YUM_REPO_RPMS,
    FAKE_1_YUM_REPOS_COUNT,
    FAKE_3_YUM_REPO,
    FAKE_3_YUM_REPOS_COUNT,
    PULP_PUBLISHED_YUM_REPOS_PATH,
)
from robottelo.decorators import (
    bz_bug_is_open,
    run_in_one_thread,
    skip_if_not_set,
    tier4,
)
from robottelo.helpers import create_repo, form_repo_path, md5_by_url
from robottelo.host_info import get_repo_rpms, get_repomd_revision
from robottelo.vm import VirtualMachine
from robottelo.vm_capsule import CapsuleVirtualMachine
from robottelo.test import APITestCase


@run_in_one_thread
class ContentManagementTestCase(APITestCase):
    """Content Management related tests, which exercise katello with pulp
    interactions.
    """

    @classmethod
    @skip_if_not_set('capsule', 'clients', 'fake_manifest')
    def setUpClass(cls):
        """Create a separate capsule for tests"""
        super(ContentManagementTestCase, cls).setUpClass()
        cls.capsule_vm = CapsuleVirtualMachine()
        cls.capsule_vm.create()
        # for debugging purposes. you may replace these 2 variables with your
        # capsule values and comment lines above to speed up test execution
        cls.capsule_id = cls.capsule_vm.capsule['id']
        cls.capsule_hostname = cls.capsule_vm.hostname

    @classmethod
    def tearDownClass(cls):
        """Destroy the capsule"""
        cls.capsule_vm.destroy()
        super(ContentManagementTestCase, cls).tearDownClass()

    @tier4
    def test_positive_capsule_sync(self):
        """Create repository, add it to lifecycle environment, assign lifecycle
        environment with a capsule, sync repository, sync it once again, update
        repository (add 1 new package), sync repository once again.

        @id: 35513099-c918-4a8e-90d0-fd4c87ad2f82

        @BZ: 1388296

        @expectedresults:

        1. Repository sync triggers capsule sync
        2. After syncing capsule contains same repo content as satellite
        3. Syncing repository which has no changes for a second time does not
           trigger any new publish task
        4. Repository revision on capsule remains exactly the same after second
           repo sync with no changes
        5. Syncing repository which was updated will update the content on
           capsule

        """
        repo_name = gen_string('alphanumeric')
        # Create and publish custom repository with 2 packages in it
        repo_url = create_repo(
            repo_name,
            FAKE_1_YUM_REPO,
            FAKE_1_YUM_REPO_RPMS[0:2],
        )
        # Create organization, product, repository in satellite, and lifecycle
        # environment
        org = entities.Organization(smart_proxy=[self.capsule_id]).create()
        product = entities.Product(organization=org).create()
        repo = entities.Repository(
            product=product,
            url=repo_url,
        ).create()
        lce = entities.LifecycleEnvironment(organization=org).create()
        # Associate the lifecycle environment with the capsule
        capsule = entities.Capsule(id=self.capsule_id).read()
        capsule.content_add_lifecycle_environment(data={
            'environment_id': lce.id,
        })
        result = capsule.content_lifecycle_environments()
        self.assertGreaterEqual(len(result['results']), 1)
        self.assertIn(
            lce.id, [capsule_lce['id'] for capsule_lce in result['results']])
        # Create a content view with the repository
        cv = entities.ContentView(
            organization=org,
            repository=[repo],
        ).create()
        # Sync repository
        repo.sync()
        repo = repo.read()
        # Publish new version of the content view
        cv.publish()
        cv = cv.read()
        self.assertEqual(len(cv.version), 1)
        cvv = cv.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time']
        )
        # Assert that the content of the published content view in
        # lifecycle environment is exactly the same as content of
        # repository
        lce_repo_path = form_repo_path(
            org=org.label,
            lce=lce.label,
            cv=cv.label,
            prod=product.label,
            repo=repo.label,
        )
        cvv_repo_path = form_repo_path(
            org=org.label,
            cv=cv.label,
            cvv=cvv.version,
            prod=product.label,
            repo=repo.label,
        )
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        sync_status = capsule.content_get_sync()
        last_sync_time = sync_status['last_sync_time']

        # If BZ1439691 is open, need to sync repo once more, as repodata
        # will change on second attempt even with no changes in repo
        if bz_bug_is_open(1439691):
            repo.sync()
            repo = repo.read()
            cv.publish()
            cv = cv.read()
            self.assertEqual(len(cv.version), 2)
            cvv = cv.version[-1].read()
            promote(cvv, lce.id)
            cvv = cvv.read()
            self.assertEqual(len(cvv.environment), 2)
            sync_status = capsule.content_get_sync()
            self.assertTrue(
                len(sync_status['active_sync_tasks']) >= 1 or
                sync_status['last_sync_time'] != last_sync_time
            )
            for task in sync_status['active_sync_tasks']:
                entities.ForemanTask(id=task['id']).poll()
            sync_status = capsule.content_get_sync()
            last_sync_time = sync_status['last_sync_time']

        # Assert that the content published on the capsule is exactly the
        # same as in repository on satellite
        lce_revision_capsule = get_repomd_revision(
            lce_repo_path, hostname=self.capsule_hostname)
        self.assertEqual(
            get_repo_rpms(lce_repo_path, hostname=self.capsule_hostname),
            get_repo_rpms(cvv_repo_path)
        )
        # Sync repository for a second time
        result = repo.sync()
        # Assert that the task summary contains a message that says the
        # publish was skipped because content had not changed
        self.assertEqual(result['result'], 'success')
        self.assertTrue(result['output']['post_sync_skipped'])
        self.assertEqual(
            result['humanized']['output'],
            'No new packages.'
        )
        # Publish a new version of content view
        cv.publish()
        cv = cv.read()
        cvv = cv.version[-1].read()
        # Promote new content view version to lifecycle environment
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Wait till capsule sync finishes
        sync_status = capsule.content_get_sync()
        tasks = []
        if not sync_status['active_sync_tasks']:
            self.assertNotEqual(
                sync_status['last_sync_time'], last_sync_time)
        else:
            for task in sync_status['active_sync_tasks']:
                tasks.append(entities.ForemanTask(id=task['id']))
                tasks[-1].poll()
        # Assert that the value of repomd revision of repository in
        # lifecycle environment on the capsule has not changed
        new_lce_revision_capsule = get_repomd_revision(
            lce_repo_path, hostname=self.capsule_hostname)
        self.assertEqual(lce_revision_capsule, new_lce_revision_capsule)
        # Update a repository with 1 new rpm
        create_repo(
            repo_name,
            FAKE_1_YUM_REPO,
            FAKE_1_YUM_REPO_RPMS[-1:],
        )
        # Sync, publish and promote the repository
        repo.sync()
        repo = repo.read()
        cv.publish()
        cv = cv.read()
        cvv = cv.version[-1].read()
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time'] != last_sync_time
        )
        # Assert that packages count in the repository is updated
        self.assertEqual(repo.content_counts['package'], 3)
        # Assert that the content of the published content view in
        # lifecycle environment is exactly the same as content of the
        # repository
        cvv_repo_path = form_repo_path(
            org=org.label,
            cv=cv.label,
            cvv=cvv.version,
            prod=product.label,
            repo=repo.label,
        )
        self.assertEqual(
            repo.content_counts['package'],
            cvv.package_count,
        )
        self.assertEqual(
            get_repo_rpms(lce_repo_path),
            get_repo_rpms(cvv_repo_path)
        )
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        # Assert that the content published on the capsule is exactly the
        # same as in the repository
        self.assertEqual(
            get_repo_rpms(lce_repo_path, hostname=self.capsule_hostname),
            get_repo_rpms(cvv_repo_path)
        )

    @tier4
    def test_positive_on_demand_sync(self):
        """Create a repository with 'on_demand' sync, add it to lifecycle
        environment with a capsule, sync repository, examine existing packages
        on capsule, download any package, examine packages once more

        @id: ba470269-a7ad-4181-bc7c-8e17a177ca20

        @expectedresults:

        1. After initial syncing only symlinks are present on both satellite
           and capsule, no real packages were fetched.
        2. All the symlinks are pointing to non-existent files.
        3. Attempt to download package is successful
        4. Downloaded package checksum matches checksum of the source package

        """
        repo_url = FAKE_3_YUM_REPO
        packages_count = FAKE_3_YUM_REPOS_COUNT
        package = FAKE_1_YUM_REPO_RPMS[0]
        # Create organization, product, repository in satellite, and lifecycle
        # environment
        org = entities.Organization().create()
        prod = entities.Product(organization=org).create()
        repo = entities.Repository(
            download_policy='on_demand',
            mirror_on_sync=True,
            product=prod,
            url=repo_url,
        ).create()
        lce = entities.LifecycleEnvironment(organization=org).create()
        # Associate the lifecycle environment with the capsule
        capsule = entities.Capsule(id=self.capsule_id).read()
        capsule.content_add_lifecycle_environment(data={
            'environment_id': lce.id,
        })
        result = capsule.content_lifecycle_environments()
        self.assertGreaterEqual(len(result['results']), 1)
        self.assertIn(
            lce.id,
            [capsule_lce['id'] for capsule_lce in result['results']]
        ),
        # Create a content view with the repository
        cv = entities.ContentView(
            organization=org,
            repository=[repo],
        ).create()
        # Sync repository
        repo.sync()
        repo = repo.read()
        # Publish new version of the content view
        cv.publish()
        cv = cv.read()
        self.assertEqual(len(cv.version), 1)
        cvv = cv.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time']
        )
        # Check whether the symlinks for all the packages were created on
        # satellite
        cvv_repo_path = form_repo_path(
            org=org.label,
            cv=cv.label,
            cvv=cvv.version,
            prod=prod.label,
            repo=repo.label,
        )
        result = ssh.command('find {}/ -type l'.format(cvv_repo_path))
        self.assertEqual(result.return_code, 0)
        links = set(link for link in result.stdout if link)
        self.assertEqual(len(links), packages_count)
        # Ensure all the symlinks on satellite are broken (pointing to
        # nonexistent files)
        result = ssh.command(
            'find {}/ -type l ! -exec test -e {{}} \; -print'
            .format(cvv_repo_path)
        )
        self.assertEqual(result.return_code, 0)
        broken_links = set(link for link in result.stdout if link)
        self.assertEqual(len(broken_links), packages_count)
        self.assertEqual(broken_links, links)
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        lce_repo_path = form_repo_path(
            org=org.label,
            lce=lce.label,
            cv=cv.label,
            prod=prod.label,
            repo=repo.label,
        )
        # Check whether the symlinks for all the packages were created on
        # capsule
        result = ssh.command(
            'find {}/ -type l'.format(lce_repo_path),
            hostname=self.capsule_hostname,
        )
        self.assertEqual(result.return_code, 0)
        links = set(link for link in result.stdout if link)
        self.assertEqual(len(links), packages_count)
        # Ensure all the symlinks on capsule are broken (pointing to
        # nonexistent files)
        result = ssh.command(
            'find {}/ -type l ! -exec test -e {{}} \; -print'
            .format(lce_repo_path),
            hostname=self.capsule_hostname,
        )
        self.assertEqual(result.return_code, 0)
        broken_links = set(link for link in result.stdout if link)
        self.assertEqual(len(broken_links), packages_count)
        self.assertEqual(broken_links, links)
        # Download package from satellite and get its md5 checksum
        published_repo_url = 'http://{}{}/pulp/{}/'.format(
            settings.server.hostname,
            ':{}'.format(settings.server.port) if settings.server.port else '',
            lce_repo_path.split('http/')[1]
        )
        package_md5 = md5_by_url('{}{}'.format(repo_url, package))
        # Get md5 checksum of source package
        published_package_md5 = md5_by_url(
            '{}{}'.format(published_repo_url, package))
        # Assert checksums are matching
        self.assertEqual(package_md5, published_package_md5)

    @tier4
    def test_positive_mirror_on_sync(self):
        """Create 2 repositories with 'on_demand' download policy and mirror on
        sync option, associate them with capsule, sync first repo, move package
        from first repo to second one, sync it, attempt to install package on
        some host.

        @id: 39149642-1e7e-4ef8-8762-bec295913014

        @BZ: 1409856

        @expectedresults: host, subscribed to second repo only, can
            successfully install package
        """
        repo1_name = gen_string('alphanumeric')
        repo2_name = gen_string('alphanumeric')
        # Create and publish first custom repository with 2 packages in it
        repo1_url = create_repo(
            repo1_name,
            FAKE_1_YUM_REPO,
            FAKE_1_YUM_REPO_RPMS[1:3],
        )
        # Create and publish second repo with no packages in it
        repo2_url = create_repo(repo2_name)
        # Create organization, product, repository in satellite, and lifecycle
        # environment
        org = entities.Organization().create()
        prod1 = entities.Product(organization=org).create()
        repo1 = entities.Repository(
            download_policy='on_demand',
            mirror_on_sync=True,
            product=prod1,
            url=repo1_url,
        ).create()
        prod2 = entities.Product(organization=org).create()
        repo2 = entities.Repository(
            download_policy='on_demand',
            mirror_on_sync=True,
            product=prod2,
            url=repo2_url,
        ).create()
        lce1 = entities.LifecycleEnvironment(organization=org).create()
        lce2 = entities.LifecycleEnvironment(organization=org).create()
        # Associate the lifecycle environments with the capsule
        capsule = entities.Capsule(id=self.capsule_id).read()
        for lce_id in (lce1.id, lce2.id):
            capsule.content_add_lifecycle_environment(data={
                'environment_id': lce_id,
            })
        result = capsule.content_lifecycle_environments()
        self.assertGreaterEqual(len(result['results']), 2)
        self.assertTrue(
            {lce1.id, lce2.id}.issubset(
                [capsule_lce['id'] for capsule_lce in result['results']]),
        )
        # Create content views with the repositories
        cv1 = entities.ContentView(
            organization=org,
            repository=[repo1],
        ).create()
        cv2 = entities.ContentView(
            organization=org,
            repository=[repo2],
        ).create()
        # Sync first repository
        repo1.sync()
        repo1 = repo1.read()
        # Publish new version of the content view
        cv1.publish()
        cv1 = cv1.read()
        self.assertEqual(len(cv1.version), 1)
        cvv1 = cv1.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv1, lce1.id)
        cvv1 = cvv1.read()
        self.assertEqual(len(cvv1.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time']
        )
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        # Move one package from the first repo to second one
        ssh.command(
            'mv {} {}'.format(
                os.path.join(
                    PULP_PUBLISHED_YUM_REPOS_PATH,
                    repo1_name,
                    FAKE_1_YUM_REPO_RPMS[2],
                ),
                os.path.join(
                    PULP_PUBLISHED_YUM_REPOS_PATH,
                    repo2_name,
                    FAKE_1_YUM_REPO_RPMS[2],
                ),
            )
        )
        # Update repositories (re-trigger 'createrepo' command)
        create_repo(repo1_name)
        create_repo(repo2_name)
        # Synchronize first repository
        repo1.sync()
        cv1.publish()
        cv1 = cv1.read()
        self.assertEqual(len(cv1.version), 2)
        cvv1 = cv1.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv1, lce1.id)
        cvv1 = cvv1.read()
        self.assertEqual(len(cvv1.environment), 2)
        # Synchronize second repository
        repo2.sync()
        repo2 = repo2.read()
        self.assertEqual(repo2.content_counts['package'], 1)
        cv2.publish()
        cv2 = cv2.read()
        self.assertEqual(len(cv2.version), 1)
        cvv2 = cv2.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv2, lce2.id)
        cvv2 = cvv2.read()
        self.assertEqual(len(cvv2.environment), 2)
        # Create activation key, add subscription to second repo only
        activation_key = entities.ActivationKey(
            content_view=cv2,
            environment=lce2,
            organization=org,
        ).create()
        subscription = entities.Subscription(organization=org).search(query={
            'search': 'name={}'.format(prod2.name)}
        )[0]
        activation_key.add_subscriptions(data={
            'subscription_id': subscription.id})
        # Subscribe a host with activation key
        with VirtualMachine(distro=DISTRO_RHEL7) as client:
            client.install_katello_ca()
            client.register_contenthost(
                org.label,
                activation_key.name,
            )
            # Install the package
            package_name = FAKE_1_YUM_REPO_RPMS[2].rstrip('.rpm')
            result = client.run('yum install -y {}'.format(package_name))
            self.assertEqual(result.return_code, 0)
            # Ensure package installed
            result = client.run('rpm -qa | grep {}'.format(package_name))
            self.assertEqual(result.return_code, 0)
            self.assertIn(package_name, result.stdout[0])

    @tier4
    def test_positive_update_with_immediate_sync(self):
        """Create a repository with on_demand download policy, associate it
        with capsule, sync repo, update download policy to immediate, sync once
        more.

        @id: 511b531d-1fbe-4d64-ae31-0f9eb6625e7f

        @BZ: 1315752

        @expectedresults: content was successfully synchronized - capsule
            filesystem contains valid links to packages
        """
        repo_url = FAKE_1_YUM_REPO
        packages_count = FAKE_1_YUM_REPOS_COUNT
        # Create organization, product, repository in satellite, and lifecycle
        # environment
        org = entities.Organization().create()
        prod = entities.Product(organization=org).create()
        repo = entities.Repository(
            download_policy='on_demand',
            mirror_on_sync=True,
            product=prod,
            url=repo_url,
        ).create()
        lce = entities.LifecycleEnvironment(organization=org).create()
        # Associate the lifecycle environment with the capsule
        capsule = entities.Capsule(id=self.capsule_id).read()
        capsule.content_add_lifecycle_environment(data={
            'environment_id': lce.id,
        })
        result = capsule.content_lifecycle_environments()
        self.assertGreaterEqual(len(result['results']), 1)
        self.assertIn(
            lce.id,
            [capsule_lce['id'] for capsule_lce in result['results']]
        ),
        # Create a content view with the repository
        cv = entities.ContentView(
            organization=org,
            repository=[repo],
        ).create()
        # Sync repository
        repo.sync()
        repo = repo.read()
        # Publish new version of the content view
        cv.publish()
        cv = cv.read()
        self.assertEqual(len(cv.version), 1)
        cvv = cv.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time']
        )
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        # Update download policy to 'immediate'
        repo.download_policy = 'immediate'
        repo = repo.update(['download_policy'])
        self.assertEqual(repo.download_policy, 'immediate')
        # Sync repository once again
        repo.sync()
        repo = repo.read()
        # Publish new version of the content view
        cv.publish()
        cv = cv.read()
        self.assertEqual(len(cv.version), 2)
        cvv = cv.version[-1].read()
        # Promote content view to lifecycle environment
        promote(cvv, lce.id)
        cvv = cvv.read()
        self.assertEqual(len(cvv.environment), 2)
        # Assert that a task to sync lifecycle environment to the capsule
        # is started (or finished already)
        sync_status = capsule.content_get_sync()
        self.assertTrue(
            len(sync_status['active_sync_tasks']) >= 1 or
            sync_status['last_sync_time']
        )
        # Check whether the symlinks for all the packages were created on
        # satellite
        cvv_repo_path = form_repo_path(
            org=org.label,
            cv=cv.label,
            cvv=cvv.version,
            prod=prod.label,
            repo=repo.label,
        )
        result = ssh.command('find {}/ -type l'.format(cvv_repo_path))
        self.assertEqual(result.return_code, 0)
        links = set(link for link in result.stdout if link)
        self.assertEqual(len(links), packages_count)
        # Ensure there're no broken symlinks (pointing to nonexistent files) on
        # satellite
        result = ssh.command(
            'find {}/ -type l ! -exec test -e {{}} \; -print'.format(
                cvv_repo_path))
        self.assertEqual(result.return_code, 0)
        broken_links = set(link for link in result.stdout if link)
        self.assertEqual(len(broken_links), 0)
        # Wait till capsule sync finishes
        for task in sync_status['active_sync_tasks']:
            entities.ForemanTask(id=task['id']).poll()
        lce_repo_path = form_repo_path(
            org=org.label,
            lce=lce.label,
            cv=cv.label,
            prod=prod.label,
            repo=repo.label,
        )
        # Check whether the symlinks for all the packages were created on
        # capsule
        result = ssh.command('find {}/ -type l'.format(lce_repo_path),
                             hostname=self.capsule_hostname)
        self.assertEqual(result.return_code, 0)
        links = set(link for link in result.stdout if link)
        self.assertEqual(len(links), packages_count)
        # Ensure there're no broken symlinks (pointing to nonexistent files) on
        # capsule
        result = ssh.command(
            'find {}/ -type l ! -exec test -e {{}} \; -print'.format(
                lce_repo_path), hostname=self.capsule_hostname)
        self.assertEqual(result.return_code, 0)
        broken_links = set(link for link in result.stdout if link)
        self.assertEqual(len(broken_links), 0)