from html.parser import HTMLParser

class EventProbe(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        print(f"STARTS: {tag} {attrs}")

    def handle_data(self, data: str) -> None:
        print(f"DATA: {repr(data)}")

    def handle_endtag(self, tag: str) -> None:
        print(f"END: {tag}")

if __name__ == "__main__":
    parser = EventProbe()
    parser.feed('<table><tr><td rowspan="1">项目</td><td>账面价值</td></tr></table>')
