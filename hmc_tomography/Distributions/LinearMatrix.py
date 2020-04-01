"""Distribution classes and associated methods.
"""
from abc import ABC as _ABC
from abc import abstractmethod as _abstractmethod
from typing import List as _List
from typing import Union as _Union
import warnings as _warnings
import numpy as _numpy
import scipy as _scipy
import scipy.sparse.linalg as _sparse_linalg
import scipy.sparse as _sparse
from hmc_tomography.Distributions import _AbstractDistribution


class LinearMatrix(_AbstractDistribution):
    """Likelihood model based on a linear forward model given as
    :math:`G \\mathbf{m} = \\mathbf{d}`
    """

    def __init__(
        self,
        G: _Union[_numpy.ndarray, _sparse.spmatrix] = None,
        d: _numpy.ndarray = None,
        data_covariance: _Union[
            float, _numpy.ndarray, _sparse.spmatrix
        ] = None,
        dtype=_numpy.single,
        **kwargs,
    ):

        # Four cases:
        # 1 - Dense G, scalar/vector covariance
        # 2 - Dense G, dense covariance
        # 3 - Sparse G, scalar/vector covariance
        # 4 - Sparse G, sparse covariance
        # Any other case needs to be manually programmed

        # Get dimensionality
        self.dimensions = G.shape[1]

        # Check data vector ------------------------------------------------------------
        if not (type(d) is _numpy.ndarray and d.shape == (d.size, 1)):
            raise ValueError(
                "Didn't understand the data vector object. "
                "Should be a "
                "NumPy column vector (ndarray: [datapoints, 1]). "
                f"{type(d)}, {d.shape}"
            )

        # Check forward model matrix ---------------------------------------------------
        if type(G) is _numpy.ndarray and G.shape == (d.size, self.dimensions):
            # Dense G
            dense_matrix = True
        elif issubclass(type(G), _scipy.sparse.spmatrix) and G.shape == (
            d.size,
            self.dimensions,
        ):
            # Sparse G
            dense_matrix = False
        else:
            raise ValueError(
                "Didn't understand the forward model matrix object."
                "Should either be "
                "a NumPy square matrix (ndarray: [self.dimensions, self.dimensions]) or "
                "a SciPy spmatrix derived type (spmatrix: [self.dimensions, self.dimensions])."
            )

        # Check data covariance --------------------------------------------------------
        if type(data_covariance) is float or (
            # Scalar/vector covariance
            type(data_covariance) == _numpy.ndarray
            and data_covariance.shape == (d.size, 1)
        ):
            covariance_simple = True
        elif type(
            data_covariance
        ) is _numpy.ndarray and data_covariance.shape == (d.size, d.size,):
            # Full covariance (sparse or dense)
            covariance_simple = False
        else:
            # No idea what the user wants, or very specific case.
            raise ValueError(
                "Didn't understand the data covariance object."
                "Should either be a float,"
                "NumPy column vec       tor (ndarray: [self.dimensions, 1])"
                "or NumPy square matrix (ndarray: [self.dimensions, self.dimensions])."
            )

        # Delegate construction --------------------------------------------------------
        if covariance_simple and dense_matrix:
            self.Distribution = _LinearMatrix_dense_forward_simple_covariance(
                G, d, data_covariance, **kwargs
            )
        elif (not covariance_simple) and dense_matrix:
            self.Distribution = _LinearMatrix_dense_forward_dense_covariance(
                G, d, data_covariance, **kwargs
            )
        elif covariance_simple and (not dense_matrix):
            self.Distribution = _LinearMatrix_sparse_forward_simple_covariance(
                G, d, data_covariance, **kwargs
            )
        elif (not covariance_simple) and (not dense_matrix):
            self.Distribution = _LinearMatrix_sparse_forward_sparse_covariance(
                G, d, data_covariance, **kwargs
            )

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        """
        """
        return self.Distribution.misfit(coordinates)

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        """
        """
        return self.Distribution.gradient(coordinates)

    def generate(self):
        return self.Distribution.generate()


# 1 - Dense G, scalar/vector covariance
class _LinearMatrix_dense_forward_simple_covariance(_AbstractDistribution):
    def __init__(
        self,
        G: _numpy.ndarray = None,
        d: _numpy.ndarray = None,
        data_variance: _Union[
            float, _numpy.ndarray,
        ] = None,  # The name variance is justified, as only used on diagonal
        dtype=_numpy.single,
    ):
        self.dimensions = G.shape[1]
        self.G = G.astype(dtype)
        self.d = d.astype(dtype)
        self.data_variance = data_variance
        self.data_sigma = self.data_variance ** 0.5

        # Depending on whether the data or the model space dimension is bigger,
        # performance of the misfit and gradient algorithm differs. If the data
        # dimension is smaller than model dimension, premultiplication might be faster.
        if premultiplication is not None:
            self.premultiplication = premultiplication
        else:
            self.premultiplication = self.G.shape[0] > self.G.shape[1]

        if self.premultiplication:
            if type(self.data_variance) == float:
                invcov = _numpy.eye(self.d.size) / self.data_variance
            else:
                invcov = _numpy.diag(1.0 / self.data_variance[:, 0])

            self.GtG: _numpy.ndarray = (self.G.T @ invcov @ self.G)
            self.Gtd0: _numpy.ndarray = G.T @ invcov @ self.d
            self.dtd: float = (self.d.T @ invcov @ self.d).item()

            # Free up unnecessary variables
            del self.G, self.d, self.data_variance, self.data_sigma
        else:
            self.Gt: _numpy.ndarray = G.T

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        if self.premultiplication:
            return (
                0.5
                * (
                    coordinates.T @ (self.GtG @ coordinates - 2 * self.Gtd0)
                    + self.dtd
                ).item()
            )
        else:
            return (
                0.5
                * _numpy.linalg.norm(
                    (self.G @ coordinates - self.d) / self.data_sigma
                )
                ** 2
            )

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        if self.premultiplication:
            return self.GtG @ coordinates - self.Gtd0
        else:
            return self.Gt @ (
                (self.G @ coordinates - self.d) / self.data_variance
            )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError()


# 2 - Dense G, dense covariance
class _LinearMatrix_dense_forward_dense_covariance(_AbstractDistribution):
    def __init__(
        self,
        G: _numpy.ndarray = None,
        d: _numpy.ndarray = None,
        data_covariance: _numpy.ndarray = None,
        dtype=_numpy.single,
    ):
        self.dimensions = self.dimensions
        self.G = G.astype(dtype)
        self.d = d.astype(dtype)
        self.data_covariance = data_covariance

        # Depending on whether the data or the model space dimension is bigger,
        # performance of the misfit and gradient algorithm differs. If the data
        # dimension is smaller than model dimension, premultiplication might be faster.
        if premultiplication is not None:
            self.premultiplication = premultiplication
        else:
            self.premultiplication = self.G.shape[0] > self.G.shape[1]

        # Inverse of the data covariance as needed both with and without
        # premultiplication
        invcov = _numpy.linalg.inv(self.data_covariance)

        if self.premultiplication:
            # Precompute factors
            self.GtG: _numpy.ndarray = (self.G.T @ invcov @ self.G)
            self.Gtd0: _numpy.ndarray = G.T @ invcov @ self.d
            self.dtd: float = (self.d.T @ invcov @ self.d).item()

            # Free up unnecessary variables
            del self.G, self.d, self.data_variance, self.data_sigma
        else:
            self.Gt: _numpy.ndarray = self.G.T
            self.cholesky_upper_inv_covariance: _numpy.ndarray = numpy.linalg.cholesky(
                invcov
            ).T

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        if self.premultiplication:
            return (
                0.5
                * (
                    coordinates.T @ (self.GtG @ coordinates - 2 * self.Gtd0)
                    + self.dtd
                ).item()
            )
        else:
            return (
                0.5
                * numpy.linalg.norm(
                    self.cholesky_upper_inv_covariance @ (G @ m - d0)
                )
                ** 2
            )

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        if self.premultiplication:
            return self.GtG @ coordinates - self.Gtd0
        else:
            return (
                self.Gt @ self.inv_covariance @ (self.G @ coordinates - self.d)
            )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError()


# 3 - Sparse G, scalar vector covariance
class _LinearMatrix_sparse_forward_simple_covariance(_AbstractDistribution):
    def __init__(
        self,
        G: _scipy.sparse.spmatrix = None,
        d: _numpy.ndarray = None,
        data_variance: _Union[
            float, _numpy.ndarray,
        ] = None,  # The name variance is justified, as only used on diagonal
        dtype=_numpy.single,
        premultiplication: bool = None,
        use_mkl: bool = False,
    ):
        self.dimensions = G.shape[1]
        self.G = _scipy.sparse.csr_matrix(G, dtype=dtype)
        self.d = d.astype(dtype)
        self.data_variance = data_variance
        self.data_sigma = self.data_variance ** 0.5
        self.use_mkl = use_mkl

        # Depending on whether the data or the model space dimension is bigger,
        # performance of the misfit and gradient algorithm differs. If the data
        # dimension is smaller than model dimension, premultiplication might be faster.
        if premultiplication is not None:
            self.premultiplication = premultiplication
        else:
            self.premultiplication = self.G.shape[0] > self.G.shape[1]

        # Prepare both cases
        if self.premultiplication:
            # Compute covariance matrix for premultiplication
            if type(self.data_variance) == float:
                invcov = (
                    _scipy.sparse.eye(self.d.size).tocsr() / self.data_variance
                )
            else:
                invcov = _scipy.sparse.diags(
                    1.0 / self.data_variance[:, 0], offsets=0
                ).tocsr()

            # Precompute relevate factors
            self.GtG: _scipy.sparse.spmatrix = (self.G.T @ invcov @ self.G)
            self.Gtd0: _scipy.sparse.spmatrix = G.T @ invcov @ self.d
            self.dtd: float = (self.d.T @ invcov @ self.d).item()

            # Free up unnecessary variables
            del self.G, self.d, self.data_variance, self.data_sigma
        else:
            self.Gt: _scipy.sparse.spmatrix = self.G.T

            # Import MKL
            if use_mkl:
                try:
                    # Fails with OSError if MKL is not found
                    from hmc_tomography.Helpers.mkl_interface import (
                        sparse_gemv,
                    )

                    # MKL binding works only for sparse matrices
                    if type(G) != _sparse.csr_matrix:
                        self.G = _sparse.csr_matrix(G)

                    self.use_mkl = True

                    # Bind the needed function
                    self.sparse_gemv = sparse_gemv

                    self.Gt = _scipy.sparse.csr_matrix(self.Gt, dtype=dtype)

                except OSError:
                    _warnings.warn(
                        f"MKL not found, will evaluate matrix-vector products using SciPy.",
                        Warning,
                    )
                    self.use_mkl = False
                except Exception as e:
                    _warnings.warn(f"Not using MKL because: {e}.", Warning)
                    self.use_mkl = False

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        if self.premultiplication:
            return (
                0.5
                * (
                    coordinates.T @ (self.GtG @ coordinates - 2 * self.Gtd0)
                    + self.dtd
                ).item()
            )
        elif self.use_mkl:
            return (
                0.5
                * _numpy.linalg.norm(
                    (self.sparse_gemv(self.G, coordinates) - self.d)
                    / self.data_sigma
                )
                ** 2
            )
        else:
            return (
                0.5
                * _numpy.linalg.norm(
                    (self.G @ coordinates - self.d) / self.data_sigma
                )
                ** 2
            )

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        if self.premultiplication:
            return self.GtG @ coordinates - self.Gtd0
        elif self.use_mkl:
            return self.sparse_gemv(
                self.Gt,
                (
                    (self.sparse_gemv(self.G, coordinates) - self.d)
                    / self.data_variance
                ),
            )
        else:
            return self.Gt @ (
                (self.G @ coordinates - self.d) / self.data_variance
            )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError()


# 4 - Sparse G, sparse covariance
class _LinearMatrix_sparse_forward_sparse_covariance(_AbstractDistribution):
    def __init__(
        self,
        G: _numpy.ndarray = None,
        d: _numpy.ndarray = None,
        data_covariance: _numpy.ndarray = None,
        dtype=_numpy.single,
    ):
        self.dimensions = self.dimensions
        self.G = G.astype(dtype)
        self.d = d.astype(dtype)

        if not issubclass(type(data_covariance), _scipy.sparse.spmatrix):
            data_covariance = _scipy.sparse.csr_matrix(data_covariance)

        self.data_covariance = data_covariance

        self.Gt = self.G.T.tocsr()
        self.dt = d.T
        self.factorized_covariance = _sparse_linalg.factorized(
            self.data_covariance
        )

    def misfit(self, coordinates: _numpy.ndarray) -> float:
        return (
            0.5
            * (
                (coordinates.T @ self.Gt - self.dt)
                @ self.factorized_covariance((self.G @ coordinates - self.d))
            ).item()
        )

    def gradient(self, coordinates: _numpy.ndarray) -> _numpy.ndarray:
        return self.Gt @ self.factorized_covariance(
            self.G @ coordinates - self.d
        )

    def generate(self) -> _numpy.ndarray:
        raise NotImplementedError()