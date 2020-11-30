import hmac
import logging

from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN, HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from tabulate import tabulate

from pss_project.api.github_integration.NoisePageRepoClient import NoisePageRepoClient
from pss_project.api.github_integration.check_run import (should_initialize_check_run, initialize_check_run,
                                                          complete_check_run, cleanup_check_run,
                                                          initialize_check_run_if_missing)

from pss_project.api.constants import (GITHUB_APP_IDENTIFIER, ALLOWED_EVENTS, CI_STATUS_CONTEXT,
                                       WEBHOOK_SECRET, GITHUB_WEBHOOK_HASH_HEADER, GITHUB_PRIVATE_KEY)

logger = logging.getLogger()


class GitEventsViewSet(ViewSet):

    def create(self, request):
        """ This is the endpoint that Github events are posted to """
        if not is_valid_github_webhook_hash(request.META.get(GITHUB_WEBHOOK_HASH_HEADER), request.body):
            return Response({"message": "Invalid request hash. Only Github may call this endpoint."}, status=HTTP_403_FORBIDDEN)
        logger.debug('Valid webhook hash')

        payload = JSONParser().parse(request)
        event = request.META.get('HTTP_X_GITHUB_EVENT')

        logger.debug(f'Incoming {event} event')
        if not any([valid_event == event for valid_event in ALLOWED_EVENTS]):
            return Response({"message": f"This app is only designed to handle {ALLOWED_EVENTS} events"},
                            status=HTTP_400_BAD_REQUEST)

        try:
            repo_client = NoisePageRepoClient(private_key=GITHUB_PRIVATE_KEY, app_id=GITHUB_APP_IDENTIFIER)
            logger.debug('Authenticated with Github repo')

            if(not repo_client.is_valid_installation_id(payload.get('installation', {}).get('id'))):
                return Response({"message": "This app only works with the NoisePage repo"}, status=HTTP_400_BAD_REQUEST)

            if event == 'pull_request':
                handle_pull_request_event(repo_client, payload)
            if event == 'status':
                handle_status_event(repo_client, payload)

        except Exception as err:
            return Response({"message": err.message if hasattr(err, 'message') else err}, status=HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=HTTP_200_OK)


def is_valid_github_webhook_hash(hash_header, req_body):
    """ Check that the has passed with the request is valid based on the
    webhook secret and the request body """
    alg, req_hash = hash_header.split('=', 1)
    valid_hash = hmac.new(str.encode(WEBHOOK_SECRET), req_body, alg)
    return hmac.compare_digest(req_hash, valid_hash.hexdigest())


def handle_pull_request_event(repo_client, payload):
    """ When a pull request event is detected create a new check run for the 
    performance cop"""
    # TODO: Not sure if we want some logic for labels
    # TODO: This if statement is temporary so we can test in the NoisePage repo without affecting everyone
    if payload['pull_request'].get('user', {}).get('login') == 'bialesdaniel':
        commit_sha = payload['pull_request'].get('head', {}).get('sha')
        if should_initialize_check_run(payload.get('action')):
            logger.debug('pull request reinitialized check')
            initialize_check_run(repo_client, commit_sha)
        if payload.get('action') == 'closed':
            logger.debug('pull request was closed ')
            branch = payload['pull_request'].get('head', {}).get('ref')
            cleanup_check_run(branch)


def handle_status_event(repo_client, payload):
    """ When a status update event occurs check to see if it indicates that the
    ci/cd pipeline completed. If that is the case then results will be in the 
    database. Compare the performance results with the results from master and
    update the check run based on the results of the comparison """
    commit_sha = payload.get('commit', {}).get('sha')
    status_response = repo_client.get_commit_status(commit_sha)
    if is_ci_complete(status_response):
        logger.debug('Status update indicated CI completed')
        complete_check_run(repo_client, commit_sha)
    elif status_response.get('context') == CI_STATUS_CONTEXT:
        logger.debug('Status update indicated CI started')
        initialize_check_run_if_missing(repo_client, commit_sha)


def is_ci_complete(status_reponse):
    """ Check whether a status update indicates that the Jenkins pipeline
    is complete. This is based on the state and the context of the status """
    if status_reponse.get('state') != 'success':
        return False
    return any([status.get('context') == CI_STATUS_CONTEXT for status in status_reponse.get('statuses', [])])
