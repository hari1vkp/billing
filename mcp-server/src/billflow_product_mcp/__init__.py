"""BillFlow Product Discovery MCP server.

A read-only integration that discovers product facts (names, brands, categories,
package sizes and *verified* manufacturer barcodes) from public Open Food Facts
family catalogues. It deliberately does NOT manage stock, invoices, sales,
adjustments, prices or any other BillFlow business operation.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
