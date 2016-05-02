import hashlib
import inspect
import importlib
import os
import re
from fnmatch import fnmatch

import matplotlib
import numpy as np
import pytest

import nengo
import nengo.utils.numpy as npext
from nengo.neurons import Direct, LIF, LIFRate, RectifiedLinear, Sigmoid
from nengo.rc import rc
from nengo.utils.compat import ensure_bytes, is_string
from nengo.utils.testing import Analytics, Logger, Plotter


class TestConfig(object):
    """Parameters affecting all Nengo tests.

    These are essentially global variables used by py.test to modify aspects
    of the Nengo tests. We collect them in this class to provide a
    mini namespace and to avoid using the ``global`` keyword.

    The values below are defaults. The functions in the remainder of this
    module modify these values accordingly.
    """

    test_seed = 0  # changing this will change seeds for all tests
    Simulator = nengo.Simulator
    RefSimulator = nengo.Simulator
    neuron_types = [Direct, LIF, LIFRate, RectifiedLinear, Sigmoid]


def pytest_configure(config):
    matplotlib.use('agg')

    if config.getoption('simulator'):
        TestConfig.Simulator = load_class(config.getoption('simulator')[0])
    if config.getoption('ref_simulator'):
        refsim = config.getoption('ref_simulator')[0]
        TestConfig.RefSimulator = load_class(refsim)

    if config.getoption('neurons'):
        ntypes = config.getoption('neurons')[0].split(',')
        TestConfig.neuron_types = [load_class(n) for n in ntypes]


def load_class(fully_qualified_name):
    mod_name, cls_name = fully_qualified_name.rsplit('.', 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)


@pytest.fixture(scope="session")
def Simulator(request):
    """the Simulator class being tested.

    Please use this, and not ``nengo.Simulator`` directly. If the test is
    reference simulator specific, then use ``RefSimulator`` below.
    """
    return TestConfig.Simulator


@pytest.fixture(scope="session")
def RefSimulator(request):
    """the reference simulator.

    Please use this if the test is reference simulator specific.
    Other simulators may choose to implement the same API as the
    reference simulator; this allows them to test easily.
    """
    return TestConfig.RefSimulator


def recorder_dirname(request, name):
    record = request.config.getvalue(name)
    if is_string(record):
        return record
    elif not record:
        return None

    simulator, nl = TestConfig.RefSimulator, None
    if 'Simulator' in request.funcargnames:
        simulator = request.getfuncargvalue('Simulator')
    if 'nl' in request.funcargnames:
        nl = request.getfuncargvalue('nl')
    elif 'nl_nodirect' in request.funcargnames:
        nl = request.getfuncargvalue('nl_nodirect')

    dirname = "%s.%s" % (simulator.__module__, name)
    if nl is not None:
        dirname = os.path.join(dirname, nl.__name__)
    return dirname


def parametrize_function_name(request, function_name):
    suffixes = []
    if 'parametrize' in request.keywords:
        argnames = request.keywords['parametrize'].args[::2]
        argnames = [x.strip() for names in argnames for x in names.split(',')]
        for name in argnames:
            value = request.getfuncargvalue(name)
            if inspect.isclass(value):
                value = value.__name__
            suffixes.append('{}={}'.format(name, value))
    return '+'.join([function_name] + suffixes)


@pytest.fixture
def plt(request):
    """a pyplot-compatible plotting interface.

    Please use this if your test creates plots.

    This will keep saved plots organized in a simulator-specific folder,
    with an automatically generated name. savefig() and close() will
    automatically be called when the test function completes.

    If you need to override the default filename, set `plt.saveas` to
    the desired filename.
    """
    dirname = recorder_dirname(request, 'plots')
    plotter = Plotter(
        dirname, request.module.__name__,
        parametrize_function_name(request, request.function.__name__))
    request.addfinalizer(lambda: plotter.__exit__(None, None, None))
    return plotter.__enter__()


@pytest.fixture
def analytics(request):
    """an object to store data for analytics.

    Please use this if you're concerned that accuracy or speed may regress.

    This will keep saved data organized in a simulator-specific folder,
    with an automatically generated name. Raw data (for later processing)
    can be saved with ``analytics.add_raw_data``; these will be saved in
    separate compressed ``.npz`` files. Summary data can be saved with
    ``analytics.add_summary_data``; these will be saved
    in a single ``.csv`` file.
    """
    dirname = recorder_dirname(request, 'analytics')
    analytics = Analytics(
        dirname, request.module.__name__,
        parametrize_function_name(request, request.function.__name__))
    request.addfinalizer(lambda: analytics.__exit__(None, None, None))
    return analytics.__enter__()


@pytest.fixture
def analytics_data(request):
    paths = request.config.getvalue('compare')
    function_name = parametrize_function_name(request, re.sub(
        '^test_[a-zA-Z0-9]*_', 'test_', request.function.__name__, count=1))
    return [Analytics.load(
        p, request.module.__name__, function_name) for p in paths]


@pytest.fixture
def logger(request):
    """a logging.Logger object.

    Please use this if your test emits log messages.

    This will keep saved logs organized in a simulator-specific folder,
    with an automatically generated name.
    """
    dirname = recorder_dirname(request, 'logs')
    logger = Logger(
        dirname, request.module.__name__,
        parametrize_function_name(request, request.function.__name__))
    request.addfinalizer(lambda: logger.__exit__(None, None, None))
    return logger.__enter__()


def function_seed(function, mod=0):
    c = function.__code__

    # get function file path relative to Nengo directory root
    nengo_path = os.path.abspath(os.path.dirname(nengo.__file__))
    path = os.path.relpath(c.co_filename, start=nengo_path)

    # take start of md5 hash of function file and name, should be unique
    hash_list = os.path.normpath(path).split(os.path.sep) + [c.co_name]
    hash_string = ensure_bytes('/'.join(hash_list))
    i = int(hashlib.md5(hash_string).hexdigest()[:15], 16)
    s = (i + mod) % npext.maxint
    int_s = int(s)  # numpy 1.8.0 bug when RandomState on long type inputs
    assert type(int_s) == int  # should not still be a long because < maxint
    return int_s


@pytest.fixture
def rng(request):
    """a seeded random number generator.

    This should be used in lieu of np.random because we control its seed.
    """
    # add 1 to seed to be different from `seed` fixture
    seed = function_seed(request.function, mod=TestConfig.test_seed + 1)
    return np.random.RandomState(seed)


@pytest.fixture
def seed(request):
    """a seed for seeding Networks.

    This should be used in lieu of an integer seed so that we can ensure that
    tests are not dependent on specific seeds.
    """
    return function_seed(request.function, mod=TestConfig.test_seed)


def pytest_generate_tests(metafunc):
    if "nl" in metafunc.funcargnames:
        metafunc.parametrize("nl", TestConfig.neuron_types)
    if "nl_nodirect" in metafunc.funcargnames:
        nodirect = [n for n in TestConfig.neuron_types if n is not Direct]
        metafunc.parametrize("nl_nodirect", nodirect)


def pytest_runtest_setup(item):  # noqa: C901
    rc.reload_rc([])
    rc.set('decoder_cache', 'enabled', 'False')
    rc.set('exceptions', 'simplified', 'False')

    if not hasattr(item, 'obj'):
        return

    for mark, option, message in [
            ('example', 'noexamples', "examples not requested"),
            ('slow', 'slow', "slow tests not requested")]:
        if getattr(item.obj, mark, None) and not item.config.getvalue(option):
            pytest.skip(message)

    if getattr(item.obj, 'noassertions', None):
        skipreasons = []
        for fixture_name, option, message in [
                ('analytics', 'analytics', "analytics not requested"),
                ('plt', 'plots', "plots not requested"),
                ('logger', 'logs', "logs not requested")]:
            if fixture_name in item.fixturenames:
                if item.config.getvalue(option):
                    break
                else:
                    skipreasons.append(message)
        else:
            pytest.skip(" and ".join(skipreasons))

    if 'Simulator' in item.fixturenames:
        for test, reason in TestConfig.Simulator.unsupported:
            # We add a '*' before test to eliminate the surprise of needing
            # a '*' before the name of a test function.
            if fnmatch(item.nodeid, '*' + test):
                pytest.xfail(reason)


def pytest_collection_modifyitems(session, config, items):
    compare = config.getvalue('compare') is None
    for item in list(items):
        if not hasattr(item, 'obj'):
            continue
        if (getattr(item.obj, 'compare', None) is None) != compare:
            items.remove(item)
        elif (TestConfig.Simulator is not nengo.Simulator and
                'Simulator' not in item.fixturenames):
            items.remove(item)


def pytest_terminal_summary(terminalreporter):
    reports = terminalreporter.getreports('passed')
    if not reports or terminalreporter.config.getvalue('compare') is None:
        return
    terminalreporter.write_sep("=", "PASSED")
    for rep in reports:
        for name, content in rep.sections:
            terminalreporter.writer.sep("-", name)
            terminalreporter.writer.line(content)
