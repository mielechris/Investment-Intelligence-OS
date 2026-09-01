import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import APIRouter, FastAPI

import grok_router_registry as registry


def _router(path: str) -> APIRouter:
    router = APIRouter()

    @router.get(path)
    def endpoint():
        return {"path": path}

    return router


def _router_occurrences(routes, target: APIRouter) -> int:
    count = 0
    for route in routes:
        included_router = getattr(route, "original_router", None)
        if included_router is target:
            count += 1
        if included_router is not None:
            count += _router_occurrences(getattr(included_router, "routes", ()), target)
    return count


class GrokRouterRegistryTests(unittest.TestCase):
    def _modules(self, social_router: APIRouter | None = None):
        modules = {}
        for index, name in enumerate(registry.REQUIRED_ROUTER_MODULES):
            modules[name] = SimpleNamespace(router=social_router if name == "grok_social_intelligence" else _router(f"/required/{index}"))
        for index, name in enumerate(registry.OPTIONAL_ROUTER_MODULES):
            modules[name] = SimpleNamespace(router=_router(f"/optional/{index}"))
        return modules

    def test_aggregate_router_routes_are_each_registered_once(self):
        app = FastAPI()
        social_router = _router("/grok/social/test")
        modules = self._modules(social_router)
        public_case_router = APIRouter()
        for module in modules.values():
            public_case_router.include_router(module.router)
        app.include_router(public_case_router)
        self.assertEqual(_router_occurrences(app.routes, social_router), 1)

        with patch.object(registry, "import_module", side_effect=modules.__getitem__):
            result = registry.install_grok_routers(app)

        for module_name, module in modules.items():
            self.assertEqual(_router_occurrences(app.routes, module.router), 1)
            self.assertIn(module_name, result["already_registered_modules"])
        self.assertEqual(result["modules"], [])

    def test_required_import_failure_is_fail_closed_and_does_not_echo_exception(self):
        app = FastAPI()

        with patch.object(registry, "import_module", side_effect=RuntimeError("secret-token-value")):
            with self.assertRaisesRegex(RuntimeError, "Required Grok HTTP surface failed to import: grok_social_intelligence") as raised:
                registry.install_grok_routers(app)

        self.assertNotIn("secret-token-value", str(raised.exception))

    def test_optional_import_failure_is_nonfatal_and_recorded_without_exception_text(self):
        app = FastAPI()
        modules = self._modules(_router("/grok/social/test"))
        unavailable = registry.OPTIONAL_ROUTER_MODULES[0]

        def import_module(name):
            if name == unavailable:
                raise RuntimeError("secret-token-value")
            return modules[name]

        with patch.object(registry, "import_module", side_effect=import_module):
            result = registry.install_grok_routers(app)

        self.assertIn({"module": unavailable, "status": "IMPORT_FAILED"}, result["unavailable_modules"])
        self.assertNotIn("secret-token-value", str(result))


if __name__ == "__main__":
    unittest.main()