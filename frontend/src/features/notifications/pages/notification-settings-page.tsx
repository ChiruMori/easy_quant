import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, EyeOff, Pencil, Plus, Send } from "lucide-react"
import { useRef, useState } from "react"

import { EmptyState } from "@/components/app-shell"
import { DeleteResourceButton } from "@/components/delete-resource-button"
import { IconButton } from "@/components/icon-button"
import { ListPagination } from "@/components/list-pagination"
import { PageHeader } from "@/components/page-header"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import {
  addSubscription,
  getSubscription,
  listDeliveries,
  listSubscriptionsPage,
  type Subscription,
  testSubscription,
  updateSubscription,
} from "../api"

export function NotificationSettingsPage() {
  const client = useQueryClient()
  const [channelPage, setChannelPage] = useState(1)
  const [deliveryPage, setDeliveryPage] = useState(1)
  const subscriptions = useQuery({
    queryKey: ["notifications", "subscriptions", channelPage],
    queryFn: () => listSubscriptionsPage(channelPage),
  })
  const deliveries = useQuery({
    queryKey: ["notifications", "deliveries", deliveryPage],
    queryFn: () => listDeliveries(deliveryPage),
  })
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const [editing, setEditing] = useState<Subscription | "new" | null>(null)
  const [name, setName] = useState("")
  const [channel, setChannel] = useState("ntfy")
  const [destination, setDestination] = useState("")
  const [signingSecret, setSigningSecret] = useState("")
  const [secretVisible, setSecretVisible] = useState(false)
  const [visible, setVisible] = useState(false)
  const [targets, setTargets] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState("")
  async function perform(action: () => Promise<void>, report = setError) {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    report("")
    setMessage("")
    try {
      await action()
    } catch (caught) {
      report(caught instanceof Error ? caught.message : "操作失败，请重试")
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  function closeEditor() {
    setEditing(null)
    setDestination("")
    setSigningSecret("")
    setSecretVisible(false)
    setVisible(false)
    setFormError("")
  }
  async function edit(item?: Subscription) {
    if (sending.current) return
    setEditing(item ?? "new")
    setName(item?.name ?? "")
    setChannel(item?.channel ?? "ntfy")
    setDestination("")
    setSigningSecret("")
    setSecretVisible(false)
    setVisible(false)
    setFormError("")
    if (item)
      await perform(
        async () => {
          const details = await getSubscription(item.id)
          setDestination(details.destination)
          setSigningSecret(details.signing_secret ?? "")
        },
        (message) => setFormError(message ? "原目标无法读取，请重新填写后保存。" : ""),
      )
  }
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader
        title="通知设置"
        description="实盘信号按轮汇总发送；可配置多个渠道，平台不会自动下单。"
        actions={
          <Button disabled={busy} onClick={() => void edit()}>
            <Plus data-icon="inline-start" />
            添加渠道
          </Button>
        }
      />
      {message && <p role="status">{message}</p>}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>已配置渠道</CardTitle>
          <CardDescription>
            停用后仍可编辑。目标默认隐藏，查看时仅向本人读取；保存时始终加密。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          {subscriptions.isFetching && <p role="status">正在加载通知渠道…</p>}
          {subscriptions.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {subscriptions.error.message}
                <Button variant="link" onClick={() => void subscriptions.refetch()}>
                  重试渠道列表
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {subscriptions.data && (
            <>
              {!subscriptions.data.items.length && (
                <EmptyState
                  title="尚无通知渠道"
                  message="添加邮件、ntfy 或群机器人以接收操作建议。"
                />
              )}
              {!!subscriptions.data.items.length && (
                <Table aria-label="已配置渠道" className="min-w-[680px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>渠道</TableHead>
                      <TableHead>通知目标</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {subscriptions.data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="max-w-48 truncate" title={item.name}>
                          {item.name || localizedLabel(item.channel)}
                        </TableCell>
                        <TableCell>{localizedLabel(item.channel)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className="max-w-56 truncate" title={targets[item.id]}>
                              {targets[item.id] ?? "••••••"}
                            </span>
                            <IconButton
                              icon={targets[item.id] ? EyeOff : Eye}
                              label={`${targets[item.id] ? "隐藏" : "显示"}通知目标 ${item.name || item.id}`}
                              disabled={busy}
                              variant="ghost"
                              onClick={() =>
                                void perform(async () => {
                                  if (targets[item.id])
                                    setTargets((previous) => {
                                      const next = { ...previous }
                                      delete next[item.id]
                                      return next
                                    })
                                  else {
                                    const value = await getSubscription(item.id)
                                    setTargets((previous) => ({
                                      ...previous,
                                      [item.id]: value.destination,
                                    }))
                                  }
                                })
                              }
                            />
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Switch
                              aria-label={`启用 ${item.name || item.channel}`}
                              checked={item.enabled}
                              disabled={busy}
                              onCheckedChange={(enabled) =>
                                void perform(async () => {
                                  await updateSubscription(item.id, enabled)
                                  await client.invalidateQueries({
                                    queryKey: ["notifications", "subscriptions"],
                                  })
                                })
                              }
                            />
                            <Badge variant={item.enabled ? "success" : "secondary"}>
                              {item.enabled ? "已启用" : "已停用"}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <IconButton
                              icon={Pencil}
                              label={`编辑渠道 ${item.name || item.id}`}
                              disabled={busy}
                              onClick={() => void edit(item)}
                            />
                            {item.enabled && (
                              <IconButton
                                icon={Send}
                                label={`测试连通性 ${item.name || item.id}`}
                                disabled={busy}
                                onClick={() =>
                                  void perform(async () => {
                                    const result = await testSubscription(item.id)
                                    await client.invalidateQueries({
                                      queryKey: ["notifications", "deliveries"],
                                    })
                                    setMessage(result.message)
                                  })
                                }
                              />
                            )}
                            {!item.enabled && (
                              <DeleteResourceButton
                                path={`/notifications/subscriptions/${item.id}`}
                                label="删除渠道"
                                description="将删除通知渠道及其投递记录。被实盘引用的渠道不可删除。"
                                disabled={busy}
                                onDeleted={() => {
                                  setTargets({})
                                  if (subscriptions.data.items.length === 1 && channelPage > 1)
                                    setChannelPage(channelPage - 1)
                                }}
                              />
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <ListPagination
                label="通知渠道分页"
                page={channelPage}
                pageSize={subscriptions.data.page_size}
                total={subscriptions.data.total}
                busy={busy || subscriptions.isFetching}
                onChange={(page) => {
                  setTargets({})
                  setChannelPage(page)
                }}
              />
            </>
          )}
        </CardContent>
      </Card>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>最近投递</CardTitle>
          <CardDescription>
            按投递创建时间从新到旧排列。渠道已接收表示服务接受请求，不代表终端已收到。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          {deliveries.isFetching && <p role="status">正在加载投递记录…</p>}
          {deliveries.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {deliveries.error.message}
                <Button variant="link" onClick={() => void deliveries.refetch()}>
                  重试投递列表
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {deliveries.data && (
            <>
              {!deliveries.data.items.length && (
                <EmptyState
                  title="尚无投递记录"
                  message="渠道测试和实盘信号会在这里保留投递结果。"
                />
              )}
              {!!deliveries.data.items.length && (
                <Table aria-label="最近投递" className="min-w-[680px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>创建时间</TableHead>
                      <TableHead>渠道</TableHead>
                      <TableHead>投递状态</TableHead>
                      <TableHead>尝试次数</TableHead>
                      <TableHead>诊断</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {deliveries.data.items.map((delivery) => (
                      <TableRow key={delivery.id}>
                        <TableCell>
                          {delivery.created_at || delivery.updated_at
                            ? new Date(delivery.created_at || delivery.updated_at!).toLocaleString(
                                "zh-CN",
                                { timeZone: "Asia/Shanghai" },
                              )
                            : "未记录"}
                        </TableCell>
                        <TableCell>
                          {delivery.channel === "none"
                            ? "未选择有效渠道"
                            : localizedLabel(delivery.channel)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              delivery.status === "delivered"
                                ? "success"
                                : delivery.status === "failed"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {delivery.status === "delivered"
                              ? "渠道已接收"
                              : localizedLabel(delivery.status)}
                          </Badge>
                        </TableCell>
                        <TableCell>{delivery.attempts ?? "—"}</TableCell>
                        <TableCell className="max-w-80 break-words whitespace-normal">
                          {delivery.error || "—"}
                          {delivery.error_code && `（${delivery.error_code}）`}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <ListPagination
                label="投递记录分页"
                page={deliveryPage}
                pageSize={deliveries.data.page_size}
                total={deliveries.data.total}
                busy={deliveries.isFetching}
                onChange={setDeliveryPage}
              />
            </>
          )}
        </CardContent>
      </Card>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open && !busy) closeEditor()
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "添加通知渠道" : "编辑通知渠道"}</DialogTitle>
            <DialogDescription>
              邮件填写收件地址，ntfy 填写主题或完整地址，机器人填写完整
              Webhook。目标和签名密钥均加密保存，编辑不会更改启用状态。
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex min-w-0 flex-col gap-5"
            onSubmit={(event) => {
              event.preventDefault()
              void perform(async () => {
                if (editing === "new")
                  await addSubscription(
                    channel,
                    destination,
                    name,
                    ["dingtalk", "feishu"].includes(channel) ? signingSecret : undefined,
                  )
                else if (editing)
                  await updateSubscription(
                    editing.id,
                    editing.enabled,
                    name,
                    destination,
                    ["dingtalk", "feishu"].includes(channel) ? signingSecret : undefined,
                  )
                setTargets({})
                closeEditor()
                await client.invalidateQueries({ queryKey: ["notifications", "subscriptions"] })
                setMessage("渠道已保存")
              }, setFormError)
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="channel-name">渠道名称</FieldLabel>
                <Input
                  id="channel-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  maxLength={160}
                  disabled={busy}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="notification-channel">渠道</FieldLabel>
                <Select
                  value={channel}
                  onValueChange={(value) => {
                    setChannel(value)
                    setSigningSecret("")
                    setSecretVisible(false)
                  }}
                  disabled={busy || editing !== "new"}
                >
                  <SelectTrigger id="notification-channel">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="email">邮件</SelectItem>
                      <SelectItem value="ntfy">ntfy</SelectItem>
                      <SelectItem value="dingtalk">钉钉机器人</SelectItem>
                      <SelectItem value="feishu">飞书机器人</SelectItem>
                      <SelectItem value="wecom">企业微信机器人</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="destination">通知目标</FieldLabel>
                <div className="flex min-w-0 items-center gap-2">
                  <Input
                    id="destination"
                    placeholder={
                      ["dingtalk", "feishu", "wecom"].includes(channel)
                        ? "完整 HTTPS 群机器人 Webhook 地址"
                        : undefined
                    }
                    type={visible ? "text" : "password"}
                    autoComplete="off"
                    value={destination}
                    onChange={(event) => setDestination(event.target.value)}
                    required
                    maxLength={4096}
                    disabled={busy}
                  />
                  <IconButton
                    icon={visible ? EyeOff : Eye}
                    label={visible ? "隐藏通知目标" : "显示通知目标"}
                    disabled={busy}
                    onClick={() => setVisible((value) => !value)}
                  />
                </div>
                <FieldDescription>目标仅在当前编辑窗口读取，关闭后清除。</FieldDescription>
              </Field>
              {["dingtalk", "feishu"].includes(channel) && (
                <Field>
                  <FieldLabel htmlFor="signing-secret">签名密钥（可选）</FieldLabel>
                  <div className="flex min-w-0 items-center gap-2">
                    <Input
                      id="signing-secret"
                      type={secretVisible ? "text" : "password"}
                      value={signingSecret}
                      onChange={(event) => setSigningSecret(event.target.value)}
                      maxLength={512}
                      autoComplete="off"
                      disabled={busy}
                    />
                    <IconButton
                      icon={secretVisible ? EyeOff : Eye}
                      label={secretVisible ? "隐藏签名密钥" : "显示签名密钥"}
                      disabled={busy}
                      onClick={() => setSecretVisible((value) => !value)}
                    />
                  </div>
                  <FieldDescription>
                    机器人开启签名校验时填写；未开启可留空，清空后保存可移除签名。若使用关键词校验，请设置关键词
                    Easy Quant。测试投递可查看配置是否生效。
                  </FieldDescription>
                </Field>
              )}
            </FieldGroup>
            {formError && (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}
            {busy && <p role="status">正在处理…</p>}
            <DialogFooter>
              <Button variant="outline" type="button" disabled={busy} onClick={closeEditor}>
                取消
              </Button>
              <Button type="submit" disabled={busy}>
                {editing === "new" ? "添加渠道" : "保存渠道"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
