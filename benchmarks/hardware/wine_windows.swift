import CoreGraphics
import Foundation
let opts: CGWindowListOption = [.optionAll]
guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { print("no list"); exit(1) }
var found = 0
for w in list {
    let owner = (w[kCGWindowOwnerName as String] as? String) ?? ""
    let name = (w[kCGWindowName as String] as? String) ?? ""
    if owner.lowercased().contains("wine") || owner.lowercased().contains("notepad") || name.lowercased().contains("notepad") || name.lowercased().contains("untitled") {
        found += 1
        print("owner=\(owner) name=\(name) bounds=\(w[kCGWindowBounds as String] ?? "-") onscreen=\(w[kCGWindowIsOnscreen as String] ?? "-")")
    }
}
print("wine-related windows: \(found) of \(list.count)")
