import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { localizedLabel } from "@/lib/labels"

import { listUsers, updateUser } from "../api"

export function UsersPage() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers })
  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateUser(id, { status }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "users"] }),
  })
  if (query.isLoading) return <LoadingState label="正在加载用户" />
  if (query.error) return <ErrorState title="无法加载用户" message={query.error.message} />
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <p className="text-muted-foreground">平台不开放公共注册，用户只能通过邀请码加入。</p>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>用户名</TableHead>
            <TableHead>角色</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {query.data?.map((user) => (
            <TableRow key={user.id}>
              <TableCell>{user.username}</TableCell>
              <TableCell>
                <Badge variant="secondary">{localizedLabel(user.role)}</Badge>
              </TableCell>
              <TableCell>{localizedLabel(user.status)}</TableCell>
              <TableCell>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    mutation.mutate({
                      id: user.id,
                      status: user.status === "active" ? "disabled" : "active",
                    })
                  }
                >
                  {user.status === "active" ? "停用" : "启用"}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
