// The desktop shell at Layer 0 is structure and toolchain only. The text
// interface is WP-0.10; nothing here displays state, because there is no
// authoritative state for it to display (00-charter.md invariant 29).
export function App(): React.JSX.Element {
  return (
    <main>
      <h1>Val</h1>
      <p>House Armand</p>
    </main>
  );
}
