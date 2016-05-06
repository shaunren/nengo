from nengo.utils import graphs


def test_reversedict():
    edges = graphs.graph({'a': {'b', 'c'}})
    r_edges = graphs.reverse_edges(edges)
    assert r_edges == {'b': ('a',), 'c': ('a',)}


def test_toposort():
    edges = graphs.graph({'a': {'b', 'c'}, 'b': ('c',)})
    assert graphs.toposort(edges) == ['a', 'b', 'c']


def test_transitive_closure():
    edges = graphs.graph({'a': {}, 'b': {'c', 'd'}, 'd': {'e', }})
    assert graphs.transitive_closure(edges) == {
        'a': set(), 'b': {'c', 'd', 'e'}, 'c': set(), 'd': {'e'}, 'e': set()}


def test_add_edges():
    edges = graphs.graph({'a': {'b', 'c'}})
    graphs.add_edges(edges, [('a', 'd'), ('b', 'c')])
    assert edges == {'a': {'b', 'c', 'd'}, 'b': {'c'}}
