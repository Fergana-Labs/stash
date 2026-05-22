import { Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function SelfHostingPage() {
  return (
    <>
      <Title>Self-Hosting</Title>
      <Subtitle>
        Run Stash on your own machine with Docker Compose.
      </Subtitle>

      <H3>Quick start</H3>
      <CodeBlock>{`git clone https://github.com/Fergana-Labs/stash.git
cd stash
docker compose up -d --build
curl http://localhost:3456/health   # wait for {"status":"ok"}`}</CodeBlock>
      <P>
        Then install the CLI and connect a repo:
      </P>
      <CodeBlock>{`pip install stashai   # or: uv tool install stashai
cd /path/to/your/repo
stash config base_url http://localhost:3456
stash login`}</CodeBlock>
      <P>
        The UI is at <Code>http://localhost:3457</Code>.{" "}
        <Code>stash login</Code> opens it to register and authorize the CLI.
      </P>

      <H3>Upgrading</H3>
      <CodeBlock>{`git pull
docker compose up -d --build`}</CodeBlock>
    </>
  );
}
