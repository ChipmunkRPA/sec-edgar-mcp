# Conda Package Build for SEC EDGAR MCP

This directory contains the necessary files to build a `conda` package for the `SEC EDGAR MCP` server.

## Building Locally

To build the `conda` package locally:

1. Install `conda-build`:
```
conda install conda-build
```

2. Build the package:
```
conda build conda/
```

## Package Information

This `conda` package installs:
- The `SEC EDGAR MCP` server
- All required dependencies

## Using the Package

After installation, you can register the server with:

```
mcp install sec_edgar_mcp/server.py --name "SEC EDGAR MCP" --with secedgar
```

## Anaconda Cloud

The package is available on Anaconda Cloud at:
[https://anaconda.org/stefano.amorelli/sec-edgar-mcp](https://anaconda.org/stefano.amorelli/sec-edgar-mcp)

## Maintainer

This package is maintained by [Stefano Amorelli](https://github.com/stefanoamorelli).
