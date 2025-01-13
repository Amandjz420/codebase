import logging

class LoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        self.logger.info(f"Request URL: {request.path}")
        self.logger.info(f"Request Method: {request.method}")
        self.logger.info(f"Request Body: {request.body}")

        response = self.get_response(request)

        self.logger.info(f"Response Status Code: {response.status_code}")
        self.logger.info(f"Response Content: {response.content}")

        return response
