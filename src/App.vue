<template>
  <div class="min-h-dvh text-slate-800">
    <header class="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur supports-[backdrop-filter]:bg-white/72">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div class="flex items-center gap-3">
          <div class="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 text-xs font-extrabold text-white shadow-sm">
            AV
          </div>
          <div>
            <div class="text-sm font-semibold leading-4 text-slate-900">AVS System</div>
            <div class="text-xs text-slate-500">视频发声物体分割</div>
          </div>
        </div>

        <nav class="flex items-center gap-2 text-sm">
          <RouterLink
            to="/"
            class="rounded-lg px-3 py-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            active-class="bg-slate-900 text-white shadow-sm"
            >工作台</RouterLink>
          <RouterLink
            to="/tasks"
            class="rounded-lg px-3 py-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            active-class="bg-slate-900 text-white shadow-sm"
            >任务中心</RouterLink>
          <RouterLink
            to="/admin"
            class="rounded-lg px-3 py-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            active-class="bg-slate-900 text-white shadow-sm"
            >管理员</RouterLink>
        </nav>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-6 md:py-8">
      <router-view />
    </main>
  </div>
</template>
