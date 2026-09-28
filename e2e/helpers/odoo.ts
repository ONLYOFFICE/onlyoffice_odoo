// Copyright (C) 2026 Ascensio System SIA
import { ODOO_URL } from "./env"

export const DB = "e2e"
const PASSWORD = "admin"

/** JSON-RPC client (`/jsonrpc`, `execute_kw`) for preparing and checking data outside the browser. */
export class Odoo {
  private uid?: number

  async call<T = unknown>(model: string, method: string, args: unknown[] = [], kwargs = {}): Promise<T> {
    this.uid ??= await this.rpc<number>("common", "authenticate", [DB, "admin", PASSWORD, {}])
    return this.rpc<T>("object", "execute_kw", [DB, this.uid, PASSWORD, model, method, args, kwargs])
  }

  /** One field of one record. */
  async read<T = string>(model: string, id: number, field: string): Promise<T> {
    const [record] = await this.call<Record<string, T>[]>(model, "read", [[id]], { fields: [field] })
    return record[field]
  }

  getParam(key: string) {
    return this.call<string | false>("ir.config_parameter", "get_param", [key])
  }

  setParam(key: string, value: boolean) {
    return this.call("ir.config_parameter", "set_param", [key, value])
  }

  private async rpc<T>(service: string, method: string, args: unknown[]): Promise<T> {
    const response = await fetch(`${ODOO_URL}/jsonrpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { service, method, args } }),
    })
    const { result, error } = await response.json()
    if (error) {
      throw new Error(`Odoo RPC ${service}.${method}: ${error.data?.message ?? error.message}`)
    }
    return result
  }
}
