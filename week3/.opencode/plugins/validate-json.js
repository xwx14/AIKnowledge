import { resolve, normalize, relative } from "path"
import { spawnSync } from "child_process"

const ARTICLES_DIR = "knowledge/articles"

function isArticleFile(filePath) {
  if (!filePath) return false
  const rel = relative(process.cwd(), resolve(filePath))
  return normalize(rel).startsWith(ARTICLES_DIR) && rel.endsWith(".json")
}

function getFilePathFromArgs(tool, args) {
  if (tool === "write" || tool === "edit") return args?.filePath
  if (tool === "bash") {
    const cmd = typeof args?.command === "string" ? args.command : ""
    const m = cmd.match(/(?:>|\s--output[-=])\s*["']?([^\s"']+\.(?:json))["']?/i)
    if (m) return m[1]
  }
  return null
}

export const ValidateJsonPlugin = async ({ directory }) => {
  return {
    "tool.execute.after": async (input, output) => {
      const { tool, args } = input
      const filePath = getFilePathFromArgs(tool, args)
      if (!filePath || !isArticleFile(filePath)) return

      const script = resolve(directory, "hooks", "validate_json.py")
      const target = resolve(filePath)

      const result = spawnSync(process.execPath.includes("python")
        ? process.execPath
        : "python", [script, target], {
        cwd: directory,
        encoding: "utf-8",
        timeout: 30000,
        windowsHide: true,
      })

      if (result.status !== 0) {
        const errDetail = (result.stderr || result.stdout || "").trim()
        output.metadata = output.metadata || {}
        output.metadata.validation = {
          passed: false,
          errors: errDetail,
        }
        output.title = (output.title || "") + " [校验失败]"
        output.output += "\n\n--- validate_json.py 校验结果 ---\n" + errDetail
      }
    },
  }
}
