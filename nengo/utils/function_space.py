from __future__ import absolute_import

import nengo
import numpy as np


class Function(nengo.dists.Distribution):
    def __init__(self, function, superimpose=1, **distributions):
        self.function = function
        self.distributions = distributions
        self.superimpose = superimpose
        super(Function, self).__init__()

    def sample(self, n, d=None, rng=np.random):
        # TODO: an error occurs if there are fewer samples than dimensions
        n_samples = n * self.superimpose

        kwargs = {}
        for k, v in self.distributions.items():
            if isinstance(v, nengo.dists.Distribution):
                kwargs[k] = v.sample(n_samples, rng=rng)
            else:
                kwargs[k] = np.tile(v, n_samples)
        values = []
        index = 0
        for i in range(n):
            total = []
            for j in range(self.superimpose):
                args = {k:v[index] for k, v in kwargs.items()}
                total.append(self.function(**args))
                index +=1
            values.append(np.sum(total, axis=0))
        return np.vstack(values)

    def make_stimulus_node(self, function_dist):
        """Generate a Node that can control function parameters."""
        def stimulus(t, x):
            return self.project(self.function(*x))

        return nengo.Node(stimulus, size_in=self.n_params,
                          size_out=self.n_basis)

class FunctionSpaceDistribution(nengo.dists.Distribution):
    def __init__(self, function_space, data):
        self.fs = function_space
        self.data = data
        super(FunctionSpaceDistribution, self).__init__()

    def sample(self, n, d=None, rng=np.random):
        if isinstance(self.data, nengo.dists.Distribution):
            data = self.data.sample(n, rng=rng)
        else:
            data = self.data
        return np.dot(data, self.fs.basis)

class Combined(nengo.dists.Distribution):
    def __init__(self, distributions, dimensions,
                 weights=None, normalize_weights=True):
        if weights is None:
            weights = np.ones(len(distributions))
        if normalize_weights:
            weights = weights / np.linalg.norm(weights)

        self.weights = weights
        self.distributions = distributions
        self.dimensions = dimensions
        self.n_dimensions = sum(dimensions)
        super(Combined, self).__init__()

    def sample(self, n, d=None, rng=np.random):
        assert d == self.n_dimensions

        data = [dist.sample(n, d=self.dimensions[i], rng=rng) * self.weights[i]
                for i, dist in enumerate(self.distributions)]

        return np.hstack(data)




class FunctionSpace(object):

    def __init__(self, space, n_basis, n_samples=1000, seed=None):
        self.rng = np.random.RandomState(seed=seed)
        self.space = space
        self.n_basis = n_basis
        self.n_samples = n_samples

        # these are all computed by self.compute_basis()
        self._basis = None
        self._scale = None
        self._S = None


    @property
    def basis(self):
        if self._basis is None:
            self.compute_basis()
        return self._basis

    @property
    def scale(self):
        if self._scale is None:
            self.compute_basis()
        return self._scale

    @property
    def S(self):
        if self._S is None:
            self.compute_basis()
        return self._S

    def compute_basis(self):
        if isinstance(self.space, nengo.dists.Distribution):
            data = self.space.sample(self.n_samples, rng=self.rng)
        else:
            data = self.space

        U, S, V = np.linalg.svd(data)

        proj = np.dot(data, V[:self.n_basis].T)
        self._scale = np.mean(np.linalg.norm(proj, axis=1))**2
        #self._scale = (np.mean(S[:self.n_basis])) ** 2
        #self._scale = (S[0] / self.n_basis) ** 2
        #self._scale = np.linalg.norm(S[:self.n_basis])**2
        #TODO: which of those scalings works better?
        self._basis = V[:self.n_basis].T / np.sqrt(self.scale)
        self._S = S

    def project(self, pts):
        if isinstance(pts, nengo.dists.Distribution):
            return FunctionSpaceDistribution(self, pts)
        else:
            return np.dot(pts, self.basis)

    # NOTE: might be useful to be able to have parameter to downsample 
    # right here rather than only being able to get reconstruction using n_samples
    def reconstruct(self, x):
        """Decode the function from the subspace back to points"""
        return np.dot(x, self.basis.T) * self.scale

    # TODO: is function param supposed to be used here? 
    def make_plot_node(self, domain, lines=1, n_pts=20, function=None,
                       max_x=None, min_x=None, max_y=1, min_y=-1):
        """Generate a Node with a custom GUI plot"""
        pts = domain
        indices = None
        plot_slice = slice(None)
        if len(pts) > n_pts:
            indices = np.linspace(0, len(pts) - 1, n_pts).astype(int)
            pts = pts[indices]
        elif n_pts > len(pts):
            n_pts = len(pts)

        basis = self.basis
        if indices is not None:
            basis = basis[indices]

        if max_x is None:
            max_x = np.max(pts)
        if min_x is None:
            min_x = np.min(pts)

        svg_x = (pts - min_x) * 100 / (max_x - min_x)

        colors = ["#1c73b3", "#039f74", "#d65e00",
                  "#cd79a7", "#f0e542", "#56b4ea"]

        def plot_func(t, x):
            paths = []
            for i in range(lines):
                value = x[i*self.n_basis:(i+1)*self.n_basis]
                data = np.dot(value, basis.T) * self.scale

                svg_y = (-data - min_y) * 100 / (max_y - min_y)

                path = []
                for j in range(len(data)):
                    path.append('%1.0f %1.0f' % (svg_x[j], svg_y[j]))
                paths.append('<path d="M%s" fill="none" stroke="%s"/>' %
                             ('L'.join(path), colors[i % len(colors)]))

            plot_func._nengo_html_ = '''
            <svg width="100%%" height="100%%" viewbox="0 0 100 100">%s</svg>
            ''' % (''.join(paths))
        plot_func._nengo_html_ = ''
        return nengo.Node(plot_func, size_in=self.n_basis * lines, size_out=0)

    def make_2Dplot_node(self, domain, n_pts=20):
        """Generate a Node with a custom GUI plot"""
        pts = domain
        indices = None
        plot_slice = slice(None)
        if len(pts) > n_pts: 
            indices = np.linspace(0, len(pts) - 1, n_pts).astype(int)
            old_num = len(pts)
            pts = pts[indices]
        elif n_pts > len(pts):
            n_pts = len(pts)

        basis = self.basis
        if indices is not None: 
            # TODO: do this more elegantly
            basis = basis.reshape((old_num, old_num, self.n_basis))
            # NOTE: for some reason basis[indices, indices] results in 2D output?
            basis = basis[indices] 
            basis = basis[:,indices] 
            basis = basis.reshape((-1, self.n_basis))

        def plot_func(t, x):
            values = np.dot(basis, x) * self.scale

            # put on a scale of 0 - 255
            values *= 255.0
            values = values.reshape((n_pts, n_pts))
            # flip so up isn't left rightside down
            values = np.flipud(values)

            # generate png heat map based off values
            import base64
            from PIL import Image
            import cStringIO
            png = Image.fromarray(values).convert('RGB')
            buffer = cStringIO.StringIO()
            png.save(buffer, format="JPEG")
            img_str = base64.b64encode(buffer.getvalue())

            plot_func._nengo_html_ = '''
            <svg width="100%%" height="100%%" viewbox="0 0 100 100">
            <image width="100%%" height="100%%" xlink:href="data:image/png;base64,%s">
            </svg>''' % (''.join(img_str))

        plot_func._nengo_html_ = ''
        return nengo.Node(plot_func, size_in=self.n_basis, size_out=0)

    def make_stimulus_node(self, function, n_params):
        """Generate a Node that can control function parameters."""
        def stimulus(t, x):
            return self.project(function(*x))
        return nengo.Node(stimulus, size_in=n_params,
                          size_out=self.n_basis)
