# pylint: attribute-defined-outside-init
"""Unit tests for the Docker feature.

:Requirement: Docker

:CaseAutomation: Automated

:CaseLevel: Component

:TestType: Functional

:CaseImportance: High

:Upstream: No
"""
from random import choice, randint

from fauxfactory import gen_alpha, gen_string, gen_url

from robottelo.cli.base import CLIReturnCodeError
from robottelo.cli.factory import (
    make_activation_key,
    make_content_view,
    make_lifecycle_environment,
    make_org,
    make_product_wait,  # workaround for BZ 1332650
    make_repository,
)
from robottelo.cli.activationkey import ActivationKey
from robottelo.cli.contentview import ContentView
from robottelo.cli.lifecycleenvironment import LifecycleEnvironment
from robottelo.cli.product import Product
from robottelo.cli.repository import Repository
from robottelo.config import settings
from robottelo.constants import (
    DOCKER_REGISTRY_HUB,
    DOCKER_RH_REGISTRY_UPSTREAM_NAME,
)
from robottelo.datafactory import (
    generate_strings_list,
    invalid_docker_upstream_names,
    valid_docker_repository_names,
    valid_docker_upstream_names,
)
from robottelo.decorators import (
    skip_if_bug_open,
    skip_if_not_set,
    tier1,
    tier2,
    upgrade,
)
from robottelo.test import CLITestCase

DOCKER_PROVIDER = 'Docker'
REPO_CONTENT_TYPE = 'docker'
REPO_UPSTREAM_NAME = 'busybox'


def _make_docker_repo(product_id, name=None, upstream_name=None, url=None):
    """Creates a Docker-based repository.

    :param product_id: ID of the ``Product``.
    :param str name: Name for the repository. If ``None`` then a random
        value will be generated.
    :param str upstream_name: A valid name of an existing upstream repository.
        If ``None`` then defaults to ``busybox``.
    :param str url: URL of repository. If ``None`` then defaults to
        DOCKER_REGISTRY_HUB constant.
    :return: A ``Repository`` object.
    """
    return make_repository({
        'content-type': REPO_CONTENT_TYPE,
        'docker-upstream-name': upstream_name or REPO_UPSTREAM_NAME,
        'name': name or choice(generate_strings_list(15, ['numeric', 'html'])),
        'product-id': product_id,
        'url': url or DOCKER_REGISTRY_HUB,
    })


class DockerRepositoryTestCase(CLITestCase):
    """Tests specific to performing CRUD methods against ``Docker``
    repositories.

    :CaseComponent: Repositories
    """

    @classmethod
    def setUpClass(cls):
        """Create an organization and product which can be re-used in tests."""
        super(DockerRepositoryTestCase, cls).setUpClass()
        cls.org_id = make_org()['id']

    @tier1
    def test_positive_create_with_name(self):
        """Create one Docker-type repository

        :id: e82a36c8-3265-4c10-bafe-c7e07db3be78

        :expectedresults: A repository is created with a Docker upstream
         repository.

        :CaseImportance: Critical
        """
        for name in valid_docker_repository_names():
            with self.subTest(name):
                repo = _make_docker_repo(
                    make_product_wait({'organization-id': self.org_id})['id'],
                    name,
                )
                self.assertEqual(repo['name'], name)
                self.assertEqual(
                    repo['upstream-repository-name'], REPO_UPSTREAM_NAME)
                self.assertEqual(repo['content-type'], REPO_CONTENT_TYPE)

    @tier2
    def test_positive_create_repos_using_same_product(self):
        """Create multiple Docker-type repositories

        :id: 6dd25cf4-f8b6-4958-976a-c116daf27b44

        :expectedresults: Multiple docker repositories are created with a
            Docker upstream repository and they all belong to the same product.

        :CaseLevel: Integration
        """
        product = make_product_wait({'organization-id': self.org_id})
        repo_names = set()
        for _ in range(randint(2, 5)):
            repo = _make_docker_repo(product['id'])
            repo_names.add(repo['name'])
        product = Product.info({
            'id': product['id'],
            'organization-id': self.org_id,
        })
        self.assertEqual(
            repo_names,
            set([repo_['repo-name'] for repo_ in product['content']]),
        )

    @tier2
    def test_positive_create_repos_using_multiple_products(self):
        """Create multiple Docker-type repositories on multiple
        products.

        :id: 43f4ab0d-731e-444e-9014-d663ff945f36

        :expectedresults: Multiple docker repositories are created with a
            Docker upstream repository and they all belong to their respective
            products.

        :CaseLevel: Integration
        """
        for _ in range(randint(2, 5)):
            product = make_product_wait({'organization-id': self.org_id})
            repo_names = set()
            for _ in range(randint(2, 3)):
                repo = _make_docker_repo(product['id'])
                repo_names.add(repo['name'])
            product = Product.info({
                'id': product['id'],
                'organization-id': self.org_id,
            })
            self.assertEqual(
                repo_names,
                set([repo_['repo-name'] for repo_ in product['content']]),
            )

    @tier1
    def test_positive_sync(self):
        """Create and sync a Docker-type repository

        :id: bff1d40e-181b-48b2-8141-8c86e0db62a2

        :expectedresults: A repository is created with a Docker repository and
            it is synchronized.

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        self.assertEqual(
            int(repo['content-counts']['container-image-manifests']), 0)
        Repository.synchronize({'id': repo['id']})
        repo = Repository.info({'id': repo['id']})
        self.assertGreaterEqual(
            int(repo['content-counts']['container-image-manifests']), 1)

    @tier1
    def test_positive_update_name(self):
        """Create a Docker-type repository and update its name.

        :id: 8b3a8496-e9bd-44f1-916f-6763a76b9b1b

        :expectedresults: A repository is created with a Docker upstream
            repository and that its name can be updated.

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        for new_name in valid_docker_repository_names():
            with self.subTest(new_name):
                Repository.update({
                    'id': repo['id'],
                    'new-name': new_name,
                    'url': repo['url'],
                })
                repo = Repository.info({'id': repo['id']})
                self.assertEqual(repo['name'], new_name)

    @tier1
    def test_positive_update_upstream_name(self):
        """Create a Docker-type repository and update its upstream name.

        :id: 1a6985ed-43ec-4ea6-ba27-e3870457ac56

        :expectedresults: A repository is created with a Docker upstream
            repository and that its upstream name can be updated.

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])

        for new_upstream_name in valid_docker_upstream_names():
            with self.subTest(new_upstream_name):
                Repository.update({
                    'docker-upstream-name': new_upstream_name,
                    'id': repo['id'],
                    'url': repo['url'],
                })
                repo = Repository.info({'id': repo['id']})
                self.assertEqual(
                    repo['upstream-repository-name'],
                    new_upstream_name)

    @tier1
    def test_negative_update_upstream_name(self):
        """Attempt to update upstream name for a Docker-type repository.

        :id: 798651af-28b2-4907-b3a7-7c560bf66c7c

        :expectedresults: A repository is created with a Docker upstream
            repository and that its upstream name can not be updated with
            invalid values.

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])

        for new_upstream_name in invalid_docker_upstream_names():
            with self.subTest(new_upstream_name):
                with self.assertRaises(CLIReturnCodeError) as context:
                    Repository.update({
                        'docker-upstream-name': new_upstream_name,
                        'id': repo['id'],
                        'url': repo['url'],
                    })
                self.assertIn(
                    'Validation failed: Docker upstream name',
                    str(context.exception)
                )

    @skip_if_not_set('docker')
    @tier1
    def test_positive_create_with_long_upstream_name(self):
        """Create a docker repository with upstream name longer than 30
        characters

        :id: 4fe47c02-a8bd-4630-9102-189a9d268b83

        :customerscenario: true

        :BZ: 1424689

        :expectedresults: docker repository is successfully created

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'],
            upstream_name=DOCKER_RH_REGISTRY_UPSTREAM_NAME,
            url=settings.docker.external_registry_1,
        )
        self.assertEqual(
            repo['upstream-repository-name'], DOCKER_RH_REGISTRY_UPSTREAM_NAME)

    @skip_if_not_set('docker')
    @tier1
    def test_positive_update_with_long_upstream_name(self):
        """Create a docker repository and update its upstream name with longer
        than 30 characters value

        :id: 97260cce-9677-4a3e-942b-e95e2714500a

        :BZ: 1424689

        :expectedresults: docker repository is successfully updated

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        Repository.update({
            'docker-upstream-name': DOCKER_RH_REGISTRY_UPSTREAM_NAME,
            'id': repo['id'],
            'url': settings.docker.external_registry_1,
        })
        repo = Repository.info({'id': repo['id']})
        self.assertEqual(
            repo['upstream-repository-name'], DOCKER_RH_REGISTRY_UPSTREAM_NAME)

    @tier2
    def test_positive_update_url(self):
        """Create a Docker-type repository and update its URL.

        :id: 73caacd4-7f17-42a7-8d93-3dee8b9341fa

        :expectedresults: A repository is created with a Docker upstream
            repository and that its URL can be updated.
        """
        new_url = gen_url()
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        Repository.update({
            'id': repo['id'],
            'url': new_url,
        })
        repo = Repository.info({'id': repo['id']})
        self.assertEqual(repo['url'], new_url)

    @tier1
    def test_positive_delete_by_id(self):
        """Create and delete a Docker-type repository

        :id: ab1e8228-92a8-45dc-a863-7181711f2745

        :expectedresults: A repository with a upstream repository is created
            and then deleted.

        :CaseImportance: Critical
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        Repository.delete({'id': repo['id']})
        with self.assertRaises(CLIReturnCodeError):
            Repository.info({'id': repo['id']})

    @tier2
    def test_positive_delete_random_repo_by_id(self):
        """Create Docker-type repositories on multiple products and
        delete a random repository from a random product.

        :id: d4db5eaa-7379-4788-9b72-76f2589d8f20

        :expectedresults: Random repository can be deleted from random product
            without altering the other products.
        """
        products = [
            make_product_wait({'organization-id': self.org_id})
            for _
            in range(randint(2, 5))
        ]
        repos = []
        for product in products:
            for _ in range(randint(2, 3)):
                repos.append(_make_docker_repo(product['id']))
        # Select random repository and delete it
        repo = choice(repos)
        repos.remove(repo)
        Repository.delete({'id': repo['id']})
        with self.assertRaises(CLIReturnCodeError):
            Repository.info({'id': repo['id']})
        # Verify other repositories were not touched
        for repo in repos:
            result = Repository.info({'id': repo['id']})
            self.assertIn(
                result['product']['id'],
                [product['id'] for product in products],
            )


class DockerContentViewTestCase(CLITestCase):
    """Tests specific to using ``Docker`` repositories with Content Views.

    :CaseComponent: ContentViews

    :CaseLevel: Integration
    """

    @classmethod
    def setUpClass(cls):
        """Create an organization which can be re-used in tests."""
        super(DockerContentViewTestCase, cls).setUpClass()
        cls.org_id = make_org()['id']

    def _create_and_associate_repo_with_cv(self):
        """Create a Docker-based repository and content view and associate
        them.
        """
        self.repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        self.content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': self.content_view['id'],
            'repository-id': self.repo['id'],
        })
        self.content_view = ContentView.info({
            'id': self.content_view['id']
        })
        self.assertIn(
            self.repo['id'],
            [
                repo_['id']
                for repo_
                in self.content_view['container-image-repositories']
            ],
        )

    @tier2
    def test_positive_add_docker_repo_by_id(self):
        """Add one Docker-type repository to a non-composite content view

        :id: 87d6c7bb-92f8-4a32-8ad2-2a1af896500b

        :expectedresults: A repository is created with a Docker repository and
            the product is added to a non-composite content view
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': content_view['id'],
            'repository-id': repo['id'],
        })
        content_view = ContentView.info({'id': content_view['id']})
        self.assertIn(
            repo['id'],
            [repo_['id'] for repo_ in
                content_view['container-image-repositories']],
        )

    @tier2
    def test_positive_add_docker_repos_by_id(self):
        """Add multiple Docker-type repositories to a non-composite CV.

        :id: 2eb19e28-a633-4c21-9469-75a686c83b34

        :expectedresults: Repositories are created with Docker upstream
            repositories and the product is added to a non-composite content
            view.
        """
        product = make_product_wait({'organization-id': self.org_id})
        repos = [
            _make_docker_repo(product['id'])
            for _
            in range(randint(2, 5))
        ]
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        for repo in repos:
            ContentView.add_repository({
                'id': content_view['id'],
                'repository-id': repo['id'],
            })
        content_view = ContentView.info({'id': content_view['id']})
        self.assertEqual(
            set([repo['id'] for repo in repos]),
            set([repo['id'] for repo in
                content_view['container-image-repositories']]),
        )

    @tier2
    def test_positive_add_synced_docker_repo_by_id(self):
        """Create and sync a Docker-type repository

        :id: 6f51d268-ed23-48ab-9dea-cd3571daa647

        :expectedresults: A repository is created with a Docker repository and
            it is synchronized.
        """
        repo = _make_docker_repo(
            make_product_wait({'organization-id': self.org_id})['id'])
        Repository.synchronize({'id': repo['id']})
        repo = Repository.info({'id': repo['id']})
        self.assertGreaterEqual(
            int(repo['content-counts']['container-image-manifests']), 1)
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': content_view['id'],
            'repository-id': repo['id'],
        })
        content_view = ContentView.info({'id': content_view['id']})
        self.assertIn(
            repo['id'],
            [repo_['id'] for repo_ in
                content_view['container-image-repositories']],
        )

    @tier2
    @skip_if_bug_open('bugzilla', 1359665)
    def test_positive_add_docker_repo_by_id_to_ccv(self):
        """Add one Docker-type repository to a composite content view

        :id: 8e2ef5ba-3cdf-4ef9-a22a-f1701e20a5d5

        :expectedresults: A repository is created with a Docker repository and
            the product is added to a content view which is then added to a
            composite content view.

        :BZ: 1359665
        """
        self._create_and_associate_repo_with_cv()
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'id': comp_content_view['id'],
            'component-ids': self.content_view['versions'][0]['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [component['id'] for component in comp_content_view['components']],
        )

    @tier2
    @skip_if_bug_open('bugzilla', 1359665)
    def test_positive_add_docker_repos_by_id_to_ccv(self):
        """Add multiple Docker-type repositories to a composite content view.

        :id: b79cbc97-3dba-4059-907d-19316684d569

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a random number of content
            views which are then added to a composite content view.

        :BZ: 1359665
        """
        cv_versions = []
        product = make_product_wait({'organization-id': self.org_id})
        for _ in range(randint(2, 5)):
            content_view = make_content_view({
                'composite': False,
                'organization-id': self.org_id,
            })
            repo = _make_docker_repo(product['id'])
            ContentView.add_repository({
                'id': content_view['id'],
                'repository-id': repo['id'],
            })
            ContentView.publish({'id': content_view['id']})
            content_view = ContentView.info({'id': content_view['id']})
            self.assertEqual(len(content_view['versions']), 1)
            cv_versions.append(content_view['versions'][0])
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'component-ids': [cv_version['id'] for cv_version in cv_versions],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        for cv_version in cv_versions:
            self.assertIn(
                cv_version['id'],
                [
                    component['id']
                    for component
                    in comp_content_view['components']
                ],
            )

    @tier2
    def test_positive_publish_with_docker_repo(self):
        """Add Docker-type repository to content view and publish it once.

        :id: 28480de3-ffb5-4b8e-8174-fffffeef6af4

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published only once.
        """
        self._create_and_associate_repo_with_cv()
        self.assertEqual(len(self.content_view['versions']), 0)
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id'],
        })
        self.assertEqual(len(self.content_view['versions']), 1)

    @tier2
    def test_positive_publish_with_docker_repo_composite(self):
        """Add Docker-type repository to composite CV and publish it once.

        :id: 2d75419b-73ed-4f29-ae0d-9af8d9624c87

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published once and added to a composite content view which is also
            published once.

        :BZ: 1359665
        """
        self._create_and_associate_repo_with_cv()
        self.assertEqual(len(self.content_view['versions']), 0)
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id'],
        })
        self.assertEqual(len(self.content_view['versions']), 1)
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertEqual(len(comp_content_view['versions']), 1)

    @tier2
    def test_positive_publish_multiple_with_docker_repo(self):
        """Add Docker-type repository to content view and publish it multiple
        times.

        :id: 33c1b2ee-ae8a-4a7e-8254-123d97aaaa58

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published multiple times.
        """
        self._create_and_associate_repo_with_cv()
        self.assertEqual(len(self.content_view['versions']), 0)
        publish_amount = randint(2, 5)
        for _ in range(publish_amount):
            ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id'],
        })
        self.assertEqual(len(self.content_view['versions']), publish_amount)

    @tier2
    def test_positive_publish_multiple_with_docker_repo_composite(self):
        """Add Docker-type repository to content view and publish it multiple
        times.

        :id: 014adf90-d399-4a99-badb-76ee03a2c350

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            added to a composite content view which is then published multiple
            times.

        :BZ: 1359665
        """
        self._create_and_associate_repo_with_cv()
        self.assertEqual(len(self.content_view['versions']), 0)
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        publish_amount = randint(2, 5)
        for _ in range(publish_amount):
            ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertEqual(len(comp_content_view['versions']), publish_amount)

    @tier2
    def test_positive_promote_with_docker_repo(self):
        """Add Docker-type repository to content view and publish it.
        Then promote it to the next available lifecycle-environment.

        :id: a7df98f4-0ec0-40f6-8941-3dbb776d47b9

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environment.
        """
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        self._create_and_associate_repo_with_cv()
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        cvv = ContentView.version_info({
            'id': self.content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 1)
        ContentView.version_promote({
            'id': cvv['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        cvv = ContentView.version_info({
            'id': self.content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 2)

    @tier2
    @upgrade
    def test_positive_promote_multiple_with_docker_repo(self):
        """Add Docker-type repository to content view and publish it.
        Then promote it to multiple available lifecycle-environments.

        :id: e9432bc4-a709-44d7-8e1d-00ca466aa32d

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environments.
        """
        self._create_and_associate_repo_with_cv()
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        cvv = ContentView.version_info({
            'id': self.content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 1)
        for i in range(1, randint(3, 6)):
            lce = make_lifecycle_environment({'organization-id': self.org_id})
            ContentView.version_promote({
                'id': cvv['id'],
                'to-lifecycle-environment-id': lce['id'],
            })
            cvv = ContentView.version_info({
                'id': self.content_view['versions'][0]['id'],
            })
            self.assertEqual(len(cvv['lifecycle-environments']), i+1)

    @tier2
    def test_positive_promote_with_docker_repo_composite(self):
        """Add Docker-type repository to composite content view and publish it.
        Then promote it to the next available lifecycle-environment.

        :id: fb7d132e-d7fa-4890-a0ec-746dd093513e

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environment.

        :BZ: 1359665
        """
        self._create_and_associate_repo_with_cv()
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        cvv = ContentView.version_info({
            'id': comp_content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 1)
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        ContentView.version_promote({
            'id': comp_content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        cvv = ContentView.version_info({
            'id': comp_content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 2)

    @tier2
    @upgrade
    def test_positive_promote_multiple_with_docker_repo_composite(self):
        """Add Docker-type repository to composite content view and publish it.
        Then promote it to the multiple available lifecycle-environments.

        :id: 345288d6-581b-4c07-8062-e58cb6343f1b

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environments.

        :BZ: 1359665
        """
        self._create_and_associate_repo_with_cv()
        ContentView.publish({'id': self.content_view['id']})
        self.content_view = ContentView.info({
            'id': self.content_view['id']})
        self.assertEqual(len(self.content_view['versions']), 1)
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org_id,
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        cvv = ContentView.version_info({
            'id': comp_content_view['versions'][0]['id'],
        })
        self.assertEqual(len(cvv['lifecycle-environments']), 1)
        for i in range(1, randint(3, 6)):
            lce = make_lifecycle_environment({'organization-id': self.org_id})
            ContentView.version_promote({
                'id': comp_content_view['versions'][0]['id'],
                'to-lifecycle-environment-id': lce['id'],
            })
            cvv = ContentView.version_info({
                'id': comp_content_view['versions'][0]['id'],
            })
            self.assertEqual(len(cvv['lifecycle-environments']), i+1)

    @tier2
    @upgrade
    def test_positive_name_pattern_change(self):
        """Promote content view with Docker repository to lifecycle environment.
        Change registry name pattern for that environment. Verify that repository
        name on product changed according to new pattern.

        :id: 63c99ae7-238b-40ed-8cc1-d847eb4e6d65

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        pattern_prefix = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = ("{}-<%= content_view.label %>"
                       + "/<%= repository.docker_upstream_name %>").format(
                pattern_prefix)

        repo = _make_docker_repo(
                make_product_wait({'organization-id': self.org_id})['id'],
                upstream_name=docker_upstream_name)
        Repository.synchronize({'id': repo['id']})
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': content_view['id'],
            'repository-id': repo['id'],
        })
        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        ContentView.version_promote({
            'id': content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        LifecycleEnvironment.update({
            'registry-name-pattern': new_pattern,
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        lce = LifecycleEnvironment.info({
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        repos = Repository.list({
            'environment-id': lce['id'],
            'organization-id': self.org_id,
        })

        expected_pattern = "{}-{}/{}".format(pattern_prefix,
                                             content_view['label'],
                                             docker_upstream_name).lower()
        self.assertEqual(lce['registry-name-pattern'], new_pattern)
        self.assertEqual(
                Repository.info({'id': repos[0]['id']})['container-repository-name'],
                expected_pattern)

    @tier2
    def test_positive_product_name_change_after_promotion(self):
        """Promote content view with Docker repository to lifecycle environment.
        Change product name. Verify that repository name on product changed
        according to new pattern.

        :id: 92279755-717c-415c-88b6-4cc1202072e2

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        old_prod_name = gen_string('alpha', 5)
        new_prod_name = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = "<%= content_view.label %>/<%= product.name %>"

        prod = make_product_wait({
            'organization-id': self.org_id,
            'name': old_prod_name
        })
        repo = _make_docker_repo(prod['id'],
                                 upstream_name=docker_upstream_name)
        Repository.synchronize({'id': repo['id']})
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': content_view['id'],
            'repository-id': repo['id'],
        })
        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        LifecycleEnvironment.update({
            'registry-name-pattern': new_pattern,
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        lce = LifecycleEnvironment.info({
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        ContentView.version_promote({
            'id': content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        Product.update({
            'name': new_prod_name,
            'id': prod['id'],
        })
        repos = Repository.list({
            'environment-id': lce['id'],
            'organization-id': self.org_id,
        })

        expected_pattern = "{}/{}".format(content_view['label'],
                                          old_prod_name).lower()
        self.assertEqual(lce['registry-name-pattern'], new_pattern)
        self.assertEqual(
                Repository.info({'id': repos[0]['id']})['container-repository-name'],
                expected_pattern)

        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        ContentView.version_promote({
            'id': content_view['versions'][-1]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        repos = Repository.list({
            'environment-id': lce['id'],
            'organization-id': self.org_id,
        })

        expected_pattern = "{}/{}".format(content_view['label'],
                                          new_prod_name).lower()
        self.assertEqual(
                Repository.info({'id': repos[0]['id']})['container-repository-name'],
                expected_pattern)

    @tier2
    def test_positive_repo_name_change_after_promotion(self):
        """Promote content view with Docker repository to lifecycle environment.
        Change repository name. Verify that Docker repository name on product
        changed according to new pattern.

        :id: f094baab-e823-47e0-939d-bd0d88eb1538

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        old_repo_name = gen_string('alpha', 5)
        new_repo_name = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = "<%= content_view.label %>/<%= repository.name %>"

        prod = make_product_wait({'organization-id': self.org_id})
        repo = _make_docker_repo(prod['id'],
                                 name=old_repo_name,
                                 upstream_name=docker_upstream_name)
        Repository.synchronize({'id': repo['id']})
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        ContentView.add_repository({
            'id': content_view['id'],
            'repository-id': repo['id'],
        })
        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        LifecycleEnvironment.update({
            'registry-name-pattern': new_pattern,
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        lce = LifecycleEnvironment.info({
            'id': lce['id'],
            'organization-id': self.org_id,
        })
        ContentView.version_promote({
            'id': content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        Repository.update({
            'name': new_repo_name,
            'id': repo['id'],
            'product-id': prod['id'],
        })
        repos = Repository.list({
            'environment-id': lce['id'],
            'organization-id': self.org_id,
        })

        expected_pattern = "{}/{}".format(content_view['label'],
                                          old_repo_name).lower()
        self.assertEqual(
                Repository.info({'id': repos[0]['id']})['container-repository-name'],
                expected_pattern)

        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        ContentView.version_promote({
            'id': content_view['versions'][-1]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })
        repos = Repository.list({
            'environment-id': lce['id'],
            'organization-id': self.org_id,
        })

        expected_pattern = "{}/{}".format(content_view['label'],
                                          new_repo_name).lower()
        self.assertEqual(
                Repository.info({'id': repos[0]['id']})['container-repository-name'],
                expected_pattern)

    @tier2
    def test_negative_set_non_unique_name_pattern_and_promote(self):
        """Set registry name pattern to one that does not guarantee uniqueness.
        Try to promote content view with multiple Docker repositories to
        lifecycle environment. Verify that content has not been promoted.

        :id: eaf5e7ac-93c9-46c6-b538-4d6bd73ab9fc

        :expectedresults: Content view is not promoted
        """
        docker_upstream_names = ['hello-world', 'alpine']
        new_pattern = "<%= organization.label %>"

        lce = make_lifecycle_environment({
            'organization-id': self.org_id,
            'registry-name-pattern': new_pattern,
        })

        prod = make_product_wait({'organization-id': self.org_id})
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        for docker_name in docker_upstream_names:
            repo = _make_docker_repo(prod['id'],
                                     upstream_name=docker_name)
            Repository.synchronize({'id': repo['id']})
            ContentView.add_repository({
                'id': content_view['id'],
                'repository-id': repo['id'],
            })
        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        with self.assertRaises(CLIReturnCodeError):
            ContentView.version_promote({
                'id': content_view['versions'][0]['id'],
                'to-lifecycle-environment-id': lce['id'],
            })

    @tier2
    def test_negative_promote_and_set_non_unique_name_pattern(self):
        """Promote content view with multiple Docker repositories to
        lifecycle environment. Set registry name pattern to one that
        does not guarantee uniqueness. Verify that pattern has not been
        changed.

        :id: 9f952224-084f-48d1-b2ea-85f3621becea

        :expectedresults: Registry name pattern is not changed
        """
        docker_upstream_names = ['hello-world', 'alpine']
        new_pattern = "<%= organization.label %>"

        prod = make_product_wait({'organization-id': self.org_id})
        content_view = make_content_view({
            'composite': False,
            'organization-id': self.org_id,
        })
        for docker_name in docker_upstream_names:
            repo = _make_docker_repo(prod['id'],
                                     upstream_name=docker_name)
            Repository.synchronize({'id': repo['id']})
            ContentView.add_repository({
                'id': content_view['id'],
                'repository-id': repo['id'],
            })
        ContentView.publish({'id': content_view['id']})
        content_view = ContentView.info({
            'id': content_view['id'],
        })
        lce = make_lifecycle_environment({'organization-id': self.org_id})
        ContentView.version_promote({
            'id': content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': lce['id'],
        })

        with self.assertRaises(CLIReturnCodeError):
            LifecycleEnvironment.update({
                'registry-name-pattern': new_pattern,
                'id': lce['id'],
                'organization-id': self.org_id,
            })


class DockerActivationKeyTestCase(CLITestCase):
    """Tests specific to adding ``Docker`` repositories to Activation Keys.

    :CaseComponent: ActivationKeys

    :CaseLevel: Integration
    """

    @classmethod
    def setUpClass(cls):
        """Create necessary objects which can be re-used in tests."""
        super(DockerActivationKeyTestCase, cls).setUpClass()
        cls.org = make_org()
        cls.lce = make_lifecycle_environment({
            'organization-id': cls.org['id'],
        })
        cls.product = make_product_wait({
            'organization-id': cls.org['id'],
        })
        cls.repo = _make_docker_repo(cls.product['id'])
        cls.content_view = make_content_view({
            'composite': False,
            'organization-id': cls.org['id'],
        })
        ContentView.add_repository({
            'id': cls.content_view['id'],
            'repository-id': cls.repo['id'],
        })
        cls.content_view = ContentView.info({
            'id': cls.content_view['id']
        })
        ContentView.publish({'id': cls.content_view['id']})
        cls.content_view = ContentView.info({
            'id': cls.content_view['id']})
        cls.cvv = ContentView.version_info({
            'id': cls.content_view['versions'][0]['id'],
        })
        ContentView.version_promote({
            'id': cls.content_view['versions'][0]['id'],
            'to-lifecycle-environment-id': cls.lce['id'],
        })
        cls.cvv = ContentView.version_info({
            'id': cls.content_view['versions'][0]['id'],
        })

    @tier2
    def test_positive_add_docker_repo_cv(self):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then create an activation key and associate it with the
        Docker content view.

        :id: bb128642-d39f-45c2-aa69-a4776ea536a2

        :expectedresults: Docker-based content view can be added to activation
            key
        """
        activation_key = make_activation_key({
            'content-view-id': self.content_view['id'],
            'lifecycle-environment-id': self.lce['id'],
            'organization-id': self.org['id'],
        })
        self.assertEqual(
            activation_key['content-view'], self.content_view['name'])

    @tier2
    def test_positive_remove_docker_repo_cv(self):
        """Add Docker-type repository to a non-composite content view
        and publish it. Create an activation key and associate it with the
        Docker content view. Then remove this content view from the activation
        key.

        :id: d696e5fe-1818-46ce-9499-924c96e1ef88

        :expectedresults: Docker-based content view can be added and then
            removed from the activation key.
        """
        activation_key = make_activation_key({
            'content-view-id': self.content_view['id'],
            'lifecycle-environment-id': self.lce['id'],
            'organization-id': self.org['id'],
        })
        self.assertEqual(
            activation_key['content-view'], self.content_view['name'])

        # Create another content view replace with
        another_cv = make_content_view({
            'composite': False,
            'organization-id': self.org['id'],
        })
        ContentView.publish({'id': another_cv['id']})
        another_cv = ContentView.info({
            'id': another_cv['id']})
        ContentView.version_promote({
            'id': another_cv['versions'][0]['id'],
            'to-lifecycle-environment-id': self.lce['id'],
        })

        ActivationKey.update({
            'id': activation_key['id'],
            'organization-id': self.org['id'],
            'content-view-id': another_cv['id'],
            'lifecycle-environment-id': self.lce['id'],
        })
        activation_key = ActivationKey.info({
            'id': activation_key['id'],
        })
        self.assertNotEqual(
            activation_key['content-view'], self.content_view['name'])

    @tier2
    def test_positive_add_docker_repo_ccv(self):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then add this content view to a composite content view
        and publish it. Create an activation key and associate it with the
        composite Docker content view.

        :id: 1d9b82fd-8dab-4fd9-ad35-656d712d56a2

        :expectedresults: Docker-based content view can be added to activation
            key

        :BZ: 1359665
        """
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org['id'],
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        comp_cvv = ContentView.version_info({
            'id': comp_content_view['versions'][0]['id'],
        })
        ContentView.version_promote({
            'id': comp_cvv['id'],
            'to-lifecycle-environment-id': self.lce['id'],
        })
        activation_key = make_activation_key({
            'content-view-id': comp_content_view['id'],
            'lifecycle-environment-id': self.lce['id'],
            'organization-id': self.org['id'],
        })
        self.assertEqual(
            activation_key['content-view'], comp_content_view['name'])

    @tier2
    def test_positive_remove_docker_repo_ccv(self):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then add this content view to a composite content view
        and publish it. Create an activation key and associate it with the
        composite Docker content view. Then, remove the composite content view
        from the activation key.

        :id: b4e63537-d3a8-4afa-8e18-57052b93fb4c

        :expectedresults: Docker-based composite content view can be added and
            then removed from the activation key.

        :BZ: 1359665
        """
        comp_content_view = make_content_view({
            'composite': True,
            'organization-id': self.org['id'],
        })
        ContentView.update({
            'component-ids': self.content_view['versions'][0]['id'],
            'id': comp_content_view['id'],
        })
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        self.assertIn(
            self.content_view['versions'][0]['id'],
            [
                component['id']
                for component
                in comp_content_view['components']
            ],
        )
        ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = ContentView.info({
            'id': comp_content_view['id'],
        })
        comp_cvv = ContentView.version_info({
            'id': comp_content_view['versions'][0]['id'],
        })
        ContentView.version_promote({
            'id': comp_cvv['id'],
            'to-lifecycle-environment-id': self.lce['id'],
        })
        activation_key = make_activation_key({
            'content-view-id': comp_content_view['id'],
            'lifecycle-environment-id': self.lce['id'],
            'organization-id': self.org['id'],
        })
        self.assertEqual(
            activation_key['content-view'], comp_content_view['name'])

        # Create another content view replace with
        another_cv = make_content_view({
            'composite': False,
            'organization-id': self.org['id'],
        })
        ContentView.publish({'id': another_cv['id']})
        another_cv = ContentView.info({
            'id': another_cv['id']})
        ContentView.version_promote({
            'id': another_cv['versions'][0]['id'],
            'to-lifecycle-environment-id': self.lce['id'],
        })

        ActivationKey.update({
            'id': activation_key['id'],
            'organization-id': self.org['id'],
            'content-view-id': another_cv['id'],
            'lifecycle-environment-id': self.lce['id'],
        })
        activation_key = ActivationKey.info({
            'id': activation_key['id'],
        })
        self.assertNotEqual(
            activation_key['content-view'], comp_content_view['name'])
