"""HTTP transport rules for authenticated provider requests."""

from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Neither credentials nor prompts may follow a provider redirect.
        return None


def urlopen(request: Request, *, timeout: float):
    """Open one provider request without following redirects."""
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)
