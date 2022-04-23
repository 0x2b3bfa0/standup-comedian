import collections
import os

import pendulum
import slack

from typing import Iterator, Optional

from ghapi.all import GhApi
from ghapi.page import paged


class Standup:
    def __init__(
        self,
        user: str,
        organization: Optional[str] = None,
        limit: pendulum.DateTime = (
            pendulum.now().subtract(days=3)
            if pendulum.now().day_of_week == pendulum.MONDAY else
            pendulum.now().subtract(days=1)
        ),
    ):
        self.user = user
        self.organization = organization
        self.limit = limit

    def events(self) -> Iterator:
        action = GhApi().activity.list_events_for_authenticated_user
        for page in paged(action, username=self.user):
            for event in page:
                if pendulum.parse(event.created_at) < self.limit:
                    break
                if self.organization and "org" in event:
                    if event.org.login != self.organization:
                        continue
                yield event
            else:
                continue
            break

    def text(self) -> str:
        created_issues = collections.Counter()
        commented_issues = collections.Counter()
        created_pull_requests = collections.Counter()
        commented_pull_requests = collections.Counter()
        edited_wiki_pages = collections.Counter()

        def link(repository, number, title):
            return f"_<https://github.com/{repository}/pull/{number}|{title}>_ on <https://github.com/{repository}|{repository.removeprefix('iterative/')}>"

        for event in self.events():
            if event.type in (
                "PullRequestReviewCommentEvent",
                "PullRequestReviewEvent",
            ):
                commented_pull_requests.update(
                    {
                        link(
                            event.repo.name,
                            event.payload.pull_request.number,
                            event.payload.pull_request.title,
                        ): 1
                    }
                )
            elif event.type == "PullRequestEvent" and event.payload.action == "opened":
                created_pull_requests.update(
                    {
                        link(
                            event.repo.name,
                            event.payload.pull_request.number,
                            event.payload.pull_request.title,
                        ): 1
                    }
                )
            elif event.type in ("IssueCommentEvent", "IssueEvent"):
                commented_issues.update(
                    {
                        link(
                            event.repo.name,
                            event.payload.issue.number,
                            event.payload.issue.title,
                        ): 1
                    }
                )
            elif event.type == "GollumEvent":
                for page in event.payload.pages:
                    edited_wiki_pages.update(
                        {
                            f"<https://github.com/{event.repo.name}/wiki/{page.page_name}|{event.repo.name}.wiki/{page.page_name}>": 1
                        }
                    )

        pull_requests = ""
        for title in created_pull_requests.keys():
            entry = f"• Open {title}"
            if comments := commented_pull_requests.get(title):
                entry += (
                    f" {'🔥' if comments > 10 else ''}\n"
                )
            pull_requests += entry + "\n"
        for title, count in sorted(commented_pull_requests.items(), key=lambda item: item[1], reverse=True):
            if title in created_pull_requests:
                continue
            pull_requests += (
                f"• Review {title} {'🔥' if count > 10 else ''}\n"
            )

        issues = ""
        for title in created_issues.keys():
            entry = f"• Open {title}"
            if comments := commented_issues.get(title):
                entry += (
                    f" {'🔥' if comments > 10 else ''}\n"
                )
            issues += entry + "\n"
        for title, count in sorted(commented_issues.items(), key=lambda item: item[1], reverse=True):
            if title in created_issues or title in created_pull_requests or title in commented_pull_requests:
                continue
            issues += (
                f"• Discuss {title} {'🔥' if count > 10 else ''}\n"
            )

        wiki = ""
        for title, count in edited_wiki_pages.items():
            wiki += f"• Edit {title} {'🔥' if count > 10 else ''}\n"

        return pull_requests + issues + wiki

slack.WebClient(os.getenv("SLACK_TOKEN")).chat_postMessage(
    text=Standup("0x2b3bfa0", "iterative").text(), channel="U01NS7060QJ"
)
