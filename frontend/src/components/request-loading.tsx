import { LoaderCircle } from "lucide-react"
import { useSyncExternalStore } from "react"

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { getPendingWrites, subscribePendingWrites } from "@/lib/api/client"

export function RequestLoading() {
  const pending = useSyncExternalStore(subscribePendingWrites, getPendingWrites)
  return (
    <AlertDialog open={pending > 0}>
      <AlertDialogContent size="sm" onEscapeKeyDown={(event) => event.preventDefault()}>
        <AlertDialogHeader>
          <LoaderCircle className="animate-spin" aria-hidden="true" />
          <AlertDialogTitle>正在处理，请稍候</AlertDialogTitle>
          <AlertDialogDescription role="status">请求完成后即可继续操作。</AlertDialogDescription>
        </AlertDialogHeader>
      </AlertDialogContent>
    </AlertDialog>
  )
}
