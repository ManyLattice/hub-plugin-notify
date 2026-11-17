// The hub's macOS notification helper (the plugin's mac.py builds it in the hub state folder).
//   hub-notify post <id> <title> <body> <url>   show; a click opens url
//   hub-notify remove <id>                      take the shown one away (the question is already answered)
//   no arguments — macOS launched it on a click: open the notification's url and exit
// The hub runs it through open: macOS does not let the executable notify when run directly. Exit code 3 and
// "not allowed" in stderr — macOS does not allow this helper notifications.
import AppKit
import UserNotifications

final class Helper: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {

    //MARK: - Properties

    private let center = UNUserNotificationCenter.current()
    private let args = Array(CommandLine.arguments.dropFirst())

    //MARK: - NSApplicationDelegate

    // The delegate is set before launching ends: otherwise the click macOS launched the helper with is lost.
    func applicationWillFinishLaunching(_ notification: Notification) {
        center.delegate = self
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        switch args.first {
        case "post" where args.count >= 5:
            post(id: args[1], title: args[2], body: args[3], url: args[4])
        case "remove" where args.count >= 2:
            center.removeDeliveredNotifications(withIdentifiers: [args[1]])
            finish(0, after: 0.5)
        default:
            finish(0, after: 10)
        }
    }

    //MARK: - UNUserNotificationCenterDelegate

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let link = response.notification.request.content.userInfo["url"] as? String, let url = URL(string: link) {
            NSWorkspace.shared.open(url)
        }
        completionHandler()
        finish(0, after: 0.5)
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list])
    }

    //MARK: - Private methods

    private func post(id: String, title: String, body: String, url: String) {
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else {
                FileHandle.standardError.write(Data("notifications are not allowed\n".utf8))
                self.finish(3, after: 0)
                return
            }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            content.userInfo = ["url": url]
            self.center.add(UNNotificationRequest(identifier: id, content: content, trigger: nil)) { error in
                if let error {
                    FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                }
                self.finish(error == nil ? 0 : 1, after: 0)
            }
        }
    }

    private func finish(_ code: Int32, after delay: Double) {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { exit(code) }
    }
}

let app = NSApplication.shared
let helper = Helper()
app.delegate = helper
app.setActivationPolicy(.prohibited)
app.run()
