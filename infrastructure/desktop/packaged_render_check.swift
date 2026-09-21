// Does the shipped desktop actually render a persisted attachment? — macOS only.
//
//     swift infrastructure/desktop/packaged_render_check.swift
//
// Owner acceptance failure, 21 September 2026. The desktop's own unit tests
// passed while Lord Armand saw no image, because a unit test renders the
// component in jsdom and jsdom has no content security policy, no custom
// protocol origin and no image decoder. This check closes that gap as far as a
// harness can: it runs the **built frontend** in **real WebKit**, served over
// the **tauri://localhost origin the packaged app uses**, under the **policy the
// shipped Tauri configuration declares**, read from that file so the two can
// never drift apart.
//
// It then opens the conversation the service reports as holding an attachment
// and says what is in the DOM: the <img>, its src, whether it completed, its
// natural size, its laid-out size, and every policy violation the engine raised.
//
// Requirements: the service running on the loopback port, and a build present at
// apps/desktop/dist. It reads; it writes nothing and calls no provider.
//
// **What it still does not prove.** It is not the packaged application: it does
// not exercise Tauri's own asset protocol, the bundle's Info.plist, or the copy
// of the app that macOS would choose when Lord Armand opens it — and that last
// one is exactly what failed on 21 September, so
// `infrastructure/ci/check_desktop_deployment.py` guards it separately. Final
// acceptance remains his own: quit, reopen, look.

import AppKit
import Foundation
import WebKit

let REPO = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()   // desktop
    .deletingLastPathComponent()   // infrastructure
    .deletingLastPathComponent()   // repository root
let DIST = REPO.appendingPathComponent("apps/desktop/dist").path
let CONFIG = REPO.appendingPathComponent("apps/desktop/src-tauri/tauri.conf.json")
let API = "http://127.0.0.1:8756"

func fail(_ message: String) -> Never {
    print("CHECK FAILED: \(message)")
    exit(1)
}

// The policy the desktop actually ships, read rather than restated.
func shippedCsp() -> String {
    guard let data = try? Data(contentsOf: CONFIG),
          let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let app = root["app"] as? [String: Any],
          let security = app["security"] as? [String: Any],
          let csp = security["csp"] as? String
    else { fail("could not read the csp out of \(CONFIG.path)") }
    return csp
}

// The conversation to open: whichever one the service reports as carrying an
// attachment. Named by the store rather than hard-coded, so this check does not
// rot when the evidence conversation changes.
func conversationWithAnAttachment() -> String {
    guard let listing = try? Data(contentsOf: URL(string: "\(API)/conversations")!),
          let rows = try? JSONSerialization.jsonObject(with: listing) as? [[String: Any]]
    else { fail("the service is not answering on \(API) — start it and try again") }
    for row in rows {
        guard let id = row["id"] as? String,
              let detail = try? Data(contentsOf: URL(string: "\(API)/conversations/\(id)")!),
              let parsed = try? JSONSerialization.jsonObject(with: detail) as? [String: Any],
              let messages = parsed["messages"] as? [[String: Any]]
        else { continue }
        for message in messages where !((message["attachments"] as? [Any]) ?? []).isEmpty {
            return (row["title"] as? String) ?? id
        }
    }
    fail("no conversation in the store carries an attachment, so there is nothing to render")
}

let CSP = shippedCsp()
let TITLE = conversationWithAnAttachment()
print("policy:  \(CSP)")
print("opening: \(TITLE)")

// Runs before the page's own scripts, and is not subject to the page policy, so
// it records violations the page would otherwise swallow.
let RECORDER = """
window.__violations = [];
document.addEventListener('securitypolicyviolation', function (e) {
  window.__violations.push(e.violatedDirective + ' blocked ' + e.blockedURI);
});
"""

final class SchemeHandler: NSObject, WKURLSchemeHandler {
    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        var path = task.request.url?.path ?? "/"
        if path == "/" || path.isEmpty { path = "/index.html" }
        guard let body = FileManager.default.contents(atPath: DIST + path) else {
            let missing = HTTPURLResponse(url: task.request.url!, statusCode: 404,
                                          httpVersion: "HTTP/1.1", headerFields: [:])!
            task.didReceive(missing)
            task.didFinish()
            return
        }
        let type = path.hasSuffix(".js") ? "text/javascript"
                 : path.hasSuffix(".css") ? "text/css" : "text/html"
        let response = HTTPURLResponse(
            url: task.request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": type, "Content-Security-Policy": CSP]
        )!
        task.didReceive(response)
        task.didReceive(body)
        task.didFinish()
    }
    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

let configuration = WKWebViewConfiguration()
// A clean store, so an image that appears is one the engine fetched over the
// network on this run and not one an earlier run left in the cache.
configuration.websiteDataStore = WKWebsiteDataStore.nonPersistent()
configuration.setURLSchemeHandler(SchemeHandler(), forURLScheme: "tauri")
configuration.userContentController.addUserScript(
    WKUserScript(source: RECORDER, injectionTime: .atDocumentStart, forMainFrameOnly: true)
)

let webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 1100, height: 860),
                        configuration: configuration)
let window = NSWindow(contentRect: NSRect(x: -4000, y: -4000, width: 1100, height: 860),
                      styleMask: [.titled], backing: .buffered, defer: false)
window.contentView = webView
window.orderFront(nil)

func after(_ seconds: Double, _ body: @escaping () -> Void) {
    DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: body)
}

func run(_ js: String, _ label: String, then next: @escaping (Any?) -> Void) {
    webView.evaluateJavaScript(js) { value, error in
        if let error { fail("\(label): \(error)") }
        next(value)
    }
}

final class Nav: NSObject, WKNavigationDelegate {
    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
        after(3.0) {
            let click = """
            (function () {
              var wanted = \(TITLE.prefix(20).description.debugDescription);
              var nodes = Array.prototype.slice.call(document.querySelectorAll('*'));
              for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                if (n.children.length === 0 && n.textContent && n.textContent.indexOf(wanted) === 0) {
                  (n.closest('button, li, a, [role=button]') || n).click();
                  return 'opened';
                }
              }
              return 'NOT FOUND';
            })()
            """
            run(click, "opening the conversation") { opened in
                if "\(opened ?? "")" != "opened" { fail("could not open \(TITLE)") }
                after(4.0) {
                    let report = """
                    (function () {
                      var imgs = Array.prototype.slice.call(document.querySelectorAll('.attachment img'));
                      return JSON.stringify({
                        images: imgs.length,
                        loaded: imgs.filter(function (i) { return i.complete && i.naturalWidth > 0; }).length,
                        visible: imgs.filter(function (i) { return i.clientWidth > 0 && i.clientHeight > 0; }).length,
                        detail: imgs.map(function (i) {
                          return { src: i.getAttribute('src'), natural: i.naturalWidth + 'x' + i.naturalHeight,
                                   shown: i.clientWidth + 'x' + i.clientHeight };
                        }),
                        violations: window.__violations
                      });
                    })()
                    """
                    run(report, "reading the thread") { value in
                        let text = "\(value ?? "{}")"
                        print(text)
                        guard let data = text.data(using: .utf8),
                              let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                              let images = parsed["images"] as? Int,
                              let loaded = parsed["loaded"] as? Int,
                              let visible = parsed["visible"] as? Int
                        else { fail("could not read the thread's own report") }
                        if images == 0 { fail("the thread rendered no attachment image at all") }
                        if loaded != images { fail("\(images - loaded) of \(images) image(s) did not load") }
                        if visible != images { fail("an image loaded but is laid out at zero size") }
                        print("CHECK PASSED: \(images) attachment image(s) loaded and laid out")
                        exit(0)
                    }
                }
            }
        }
    }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) {
        fail("the built frontend did not load: \(e)")
    }
}

let nav = Nav()
webView.navigationDelegate = nav
webView.load(URLRequest(url: URL(string: "tauri://localhost/index.html")!))
after(60) { fail("timed out") }

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.run()
