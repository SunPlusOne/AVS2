<template>
  <div class="min-h-dvh bg-zinc-950 text-zinc-50">
    <header class="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div class="flex items-center gap-3">
          <div class="h-9 w-9 rounded-lg bg-zinc-800" />
          <div>
            <div class="text-sm font-semibold leading-4">AVS System</div>
            <div class="text-xs text-zinc-400">视频发声物体分割</div>
          </div>
        </div>

        <nav class="flex items-center gap-2 text-sm">
          <RouterLink
            to="/"
            class="rounded-md px-3 py-2 text-zinc-200 hover:bg-zinc-900"
            active-class="bg-zinc-900 text-white"
            >工作台</RouterLink>
          <RouterLink
            to="/tasks"
            class="rounded-md px-3 py-2 text-zinc-200 hover:bg-zinc-900"
            active-class="bg-zinc-900 text-white"
            >任务中心</RouterLink>
          <RouterLink
            to="/admin"
            class="rounded-md px-3 py-2 text-zinc-200 hover:bg-zinc-900"
            active-class="bg-zinc-900 text-white"
            >管理员</RouterLink>
        </nav>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-6">
      <router-view />
    </main>
  </div>
</template>
