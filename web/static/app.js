const SORT_FIELDS = {
  nickname: "昵称",
  remark: "备注",
  uin: "QQ 号",
  uid: "UID",
  qid: "QID",
  age: "年龄",
  gender_name: "性别",
  birth_year: "出生年",
  birth_month: "出生月",
  birth_day: "出生日",
  intimacy: "亲密度",
  close_relation: "亲密关系",
  group_name: "分组",
  is_friend: "是否好友",
  is_bot: "是否机器人",
  deletion_time: "删除日期",
};

const state = {
  friends: [],
  fields: [],
  query: "",
  status: "all",
  kind: "all",
  group: "all",
  sort: [
    { field: "is_bot", direction: "asc" },
    { field: "is_friend", direction: "desc" },
    { field: "deletion_time", direction: "desc" },
    { field: "close_relation", direction: "asc" },
    { field: "intimacy", direction: "desc" },

  ],
  selected: new Set(),
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  Object.assign(els, {
    summary: document.getElementById("summary"),
    owner: document.getElementById("owner"),
    ownerName: document.getElementById("owner-name"),
    ownerSignature: document.getElementById("owner-signature"),
    ownerAvatar: document.getElementById("owner-avatar"),
    search: document.getElementById("search"),
    groupOptions: document.getElementById("group-options"),
    chips: document.getElementById("status-chips"),
    kindChips: document.getElementById("kind-chips"),
    visibleCount: document.getElementById("visible-count"),
    cards: document.getElementById("cards"),
    viewSwitch: document.getElementById("view-switch"),
    selectedCount: document.getElementById("selected-count"),
    selectVisible: document.getElementById("select-visible"),
    clear: document.getElementById("clear"),
    copy: document.getElementById("copy"),
    next: document.getElementById("next"),
    sortToggle: document.getElementById("sort-toggle"),
    sortBadge: document.getElementById("sort-badge"),
    sortPanel: document.getElementById("sort-panel"),
    sortRules: document.getElementById("sort-rules"),
    addRule: document.getElementById("add-rule"),
    toast: document.getElementById("toast"),
  });

  els.search.addEventListener("input", debounce(() => {
    state.query = els.search.value.trim().toLowerCase();
    render();
  }, 120));

  els.groupOptions.addEventListener("click", (event) => {
    const option = event.target.closest("button[data-group]");
    if (!option) return;
    state.group = option.dataset.group;
    for (const button of els.groupOptions.querySelectorAll("button[data-group]")) {
      button.setAttribute("aria-pressed", String(button === option));
    }
    render();
  });

  els.chips.addEventListener("click", (event) => {
    const chip = event.target.closest("button[data-status]");
    if (!chip) return;
    state.status = chip.dataset.status;
    for (const button of els.chips.querySelectorAll("button[data-status]")) {
      button.setAttribute("aria-pressed", String(button === chip));
    }
    render();
  });

  els.kindChips.addEventListener("click", (event) => {
    const chip = event.target.closest("button[data-kind]");
    if (!chip) return;
    state.kind = chip.dataset.kind;
    for (const button of els.kindChips.querySelectorAll("button[data-kind]")) {
      button.setAttribute("aria-pressed", String(button === chip));
    }
    render();
  });

  els.viewSwitch.addEventListener("click", (event) => {
    const option = event.target.closest("button[data-view]");
    if (!option) return;
    els.cards.classList.toggle("is-compact", option.dataset.view === "compact");
    for (const button of els.viewSwitch.querySelectorAll("button[data-view]")) {
      button.setAttribute("aria-pressed", String(button === option));
    }
  });

  els.selectVisible.addEventListener("click", () => {
    const visible = filtered();
    const allSelected = visible.length > 0 && visible.every((friend) => state.selected.has(friend.uid));
    for (const friend of visible) {
      if (allSelected) state.selected.delete(friend.uid);
      else state.selected.add(friend.uid);
    }
    render();
  });

  els.clear.addEventListener("click", () => {
    state.selected.clear();
    render();
  });

  els.copy.addEventListener("click", copySelected);
  els.next.addEventListener("click", submit);

  els.sortToggle.addEventListener("click", () => setSortPanel(els.sortPanel.hidden));

  document.addEventListener("click", (event) => {
    if (els.sortPanel.hidden) return;
    // 规则重绘会移除被点击的按钮，contains 失效，按事件路径判断是否来自浮层
    const path = event.composedPath();
    if (path.includes(els.sortPanel) || path.includes(els.sortToggle)) return;
    setSortPanel(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.sortPanel.hidden) {
      setSortPanel(false);
      els.sortToggle.focus();
    }
  });

  els.addRule.addEventListener("click", () => {
    const used = new Set(state.sort.map((rule) => rule.field));
    const field = state.fields.find((key) => !used.has(key));
    if (!field) return;
    state.sort.push({ field, direction: "asc" });
    renderSortRules();
    render();
  });

  syncSortToggle();
  renderSortRules();
  load();
});

async function load() {
  try {
    const response = await fetch("/api/friends");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.friends = await response.json();
    state.fields = state.friends.length ? Object.keys(SORT_FIELDS).filter((key) => key in state.friends[0]) : [];
    els.summary.textContent = `共 ${state.friends.length} 个用户`;
    buildGroupOptions();
    renderSortRules();
    render();
    loadOwner();
  } catch (error) {
    els.summary.textContent = "加载失败";
    els.cards.replaceChildren(element("p", "empty", `加载失败：${error.message}`));
  }
}

async function loadOwner() {
  try {
    const response = await fetch("/api/owner");
    if (!response.ok) return;
    const owner = await response.json();
    if (!owner) return;
    els.ownerName.textContent = owner.nickname || owner.remark || owner.uid;
    if (owner.signature) {
      els.ownerSignature.textContent = owner.signature;
    } else {
      els.ownerSignature.hidden = true;
    }
    if (owner.uin !== null && owner.uin !== undefined) {
      const image = document.createElement("img");
      image.src = `/api/avatar/${owner.uin}`;
      image.alt = "";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove());
      els.ownerAvatar.append(image);
    }
    els.owner.classList.add("is-ready");
  } catch {
    // 主人信息仅作展示，加载失败时保持隐藏
  }
}

function setSortPanel(open) {
  els.sortPanel.hidden = !open;
  els.sortToggle.setAttribute("aria-expanded", String(open));
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function buildGroupOptions() {
  const groups = new Map();
  let ungrouped = 0;
  for (const friend of state.friends) {
    if (friend.group_id === null) {
      ungrouped += 1;
      continue;
    }
    const entry = groups.get(friend.group_id) ?? { name: friend.group_name ?? `分组 ${friend.group_id}`, count: 0 };
    entry.count += 1;
    groups.set(friend.group_id, entry);
  }

  const options = [groupOption("all", "全部分组", state.friends.length)];
  for (const [id, entry] of [...groups].sort((left, right) => left[0] - right[0])) {
    options.push(groupOption(String(id), entry.name, entry.count));
  }
  if (ungrouped) options.push(groupOption("none", "未分组", ungrouped));
  els.groupOptions.replaceChildren(...options);
}

function groupOption(value, label, count) {
  const option = element("button", "option");
  option.type = "button";
  option.dataset.group = value;
  option.setAttribute("aria-pressed", String(state.group === value));
  option.textContent = `${label}(${count})`;
  return option;
}

function matches(friend) {
  if (state.status === "friend" && !friend.is_friend) return false;
  if (state.status === "nonfriend" && friend.is_friend) return false;
  if (state.kind === "bot" && !friend.is_bot) return false;
  if (state.kind === "human" && friend.is_bot) return false;
  if (state.group === "none" && friend.group_id !== null) return false;
  if (state.group !== "all" && state.group !== "none" && String(friend.group_id) !== state.group) return false;
  if (!state.query) return true;
  return Object.values(friend).some((value) => {
    if (typeof value === "number") return String(value).includes(state.query);
    return typeof value === "string" && value.toLowerCase().includes(state.query);
  });
}

function filtered() {
  return state.friends.filter(matches);
}

function compare(left, right, direction) {
  const leftEmpty = left === null || left === undefined || left === "";
  const rightEmpty = right === null || right === undefined || right === "";
  if (leftEmpty || rightEmpty) {
    if (leftEmpty && rightEmpty) return 0;
    return leftEmpty ? 1 : -1;
  }
  let result;
  if (typeof left === "boolean" && typeof right === "boolean") {
    result = Number(left) - Number(right);
  } else if (typeof left === "number" && typeof right === "number") {
    result = left - right;
  } else {
    result = String(left).localeCompare(String(right), "zh-CN");
  }
  return direction === "desc" ? -result : result;
}

function sortedList(list) {
  if (state.sort.length === 0) return list;
  return [...list].sort((left, right) => {
    for (const rule of state.sort) {
      const result = compare(left[rule.field], right[rule.field], rule.direction);
      if (result !== 0) return result;
    }
    return 0;
  });
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatTimestamp(ms) {
  const date = new Date(ms);
  const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}:${String(date.getSeconds()).padStart(2, "0")}`;
  return `${day} ${time}`;
}

function row(friend) {
  const item = element("label", "row");

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "row-check";
  checkbox.checked = state.selected.has(friend.uid);
  checkbox.setAttribute("aria-label", `选择 ${friend.uid}`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.selected.add(friend.uid);
    else state.selected.delete(friend.uid);
    item.classList.toggle("is-selected", checkbox.checked);
    updateSelection();
  });

  const mark = element("span", "row-mark");
  mark.setAttribute("aria-hidden", "true");

  const avatarCol = element("div", "avatar-col");
  const avatarBox = element("span", "avatar");
  if (friend.uin !== null && friend.uin !== undefined) {
    const image = document.createElement("img");
    image.src = `/api/avatar/${friend.uin}`;
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.draggable = false;
    image.addEventListener("error", () => image.remove());
    avatarBox.append(image);
  }
  avatarCol.append(avatarBox);

  const info = element("div", "row-info");
  const nameLine = element("div", "row-name");
  if (friend.remark) {
    nameLine.append(element("span", "row-remark", friend.remark));
    if (friend.nickname) nameLine.append(element("span", "row-alias", friend.nickname));
  } else {
    nameLine.append(element("span", "row-remark", friend.nickname));
  }
  info.append(nameLine);

  const meta = [
    friend.uin !== null ? String(friend.uin) : null,
    friend.qid ? `QID ${friend.qid}` : null,
    friend.intimacy !== null ? `亲密度 ${friend.intimacy}` : null,
    friend.close_relation,
    friend.gender_name,
    friend.age ? `${friend.age} 岁` : null,
  ].filter((part) => part !== null && part !== undefined);
  info.append(element("div", "row-line", meta.join(" · ")));

  const tags = element("div", "row-tags");
  if (!friend.is_friend) tags.append(element("span", "tag nonfriend", "非好友"));
  if (friend.is_bot) tags.append(element("span", "tag bot", "机器人"));
  tags.append(element("span", "tag group", friend.group_name ?? "未分组"));

  item.append(checkbox, mark, avatarCol, info, tags);
  if (friend.signature) {
    item.classList.add("has-signature");
    item.append(element("div", "row-signature", friend.signature));
  }

  const detail = element("div", "row-detail");
  detail.append(element("span", "row-uid", `UID: ${friend.uid}`));
  if (friend.deletion_time !== null) {
    detail.append(element("span", "row-deleted", `删除于 ${formatTimestamp(friend.deletion_time)}`));
  }
  item.append(detail);
  item.classList.toggle("is-selected", checkbox.checked);
  return item;
}

function syncSortToggle() {
  const count = state.sort.length;
  els.sortBadge.textContent = String(count);
  els.sortBadge.classList.toggle("is-zero", count === 0);
  els.sortToggle.setAttribute("aria-label", count ? `排序规则，共 ${count} 条` : "排序规则");
}

function renderSortRules() {
  const rules = state.sort.map(sortRule);
  if (rules.length === 0) {
    rules.push(element("p", "sort-empty", "未应用排序规则，按照原始顺序排序"));
  }
  els.sortRules.replaceChildren(...rules);
  els.addRule.disabled = state.fields.length === 0 || state.sort.length >= state.fields.length;
}

function sortRule(rule, index) {
  const rowElement = element("div", "sort-rule");
  rowElement.append(element("span", "sort-index", String(index + 1)));

  const select = document.createElement("select");
  select.setAttribute("aria-label", `排序字段 ${index + 1}`);
  for (const key of state.fields) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = SORT_FIELDS[key];
    option.selected = key === rule.field;
    option.disabled = state.sort.some((other, otherIndex) => otherIndex !== index && other.field === key);
    select.append(option);
  }
  select.addEventListener("change", () => {
    rule.field = select.value;
    renderSortRules();
    render();
  });

  const direction = element("button", "dir", rule.direction === "asc" ? "↑" : "↓");
  direction.type = "button";
  direction.setAttribute("aria-label", rule.direction === "asc" ? "升序，点击切换为降序" : "降序，点击切换为升序");
  direction.addEventListener("click", () => {
    rule.direction = rule.direction === "asc" ? "desc" : "asc";
    renderSortRules();
    render();
  });

  const remove = element("button", "remove", "×");
  remove.type = "button";
  remove.setAttribute("aria-label", `移除排序规则 ${index + 1}`);
  remove.addEventListener("click", () => {
    state.sort.splice(index, 1);
    renderSortRules();
    render();
  });

  const selectWrap = element("span", "select-wrap");
  selectWrap.append(select);
  rowElement.append(selectWrap, direction, remove);
  return rowElement;
}

function render() {
  const list = sortedList(filtered());
  els.visibleCount.textContent = `显示 ${list.length} / ${state.friends.length}`;
  syncSortToggle();
  if (list.length === 0) {
    els.cards.replaceChildren(element("p", "empty", "没有符合条件的用户"));
  } else {
    els.cards.replaceChildren(...list.map(row));
  }
  updateSelection();
}

function updateSelection() {
  const count = state.selected.size;
  els.selectedCount.textContent = `已选 ${count}`;
  for (const button of [els.copy, els.next, els.clear]) {
    button.disabled = count === 0;
  }
  els.copy.setAttribute("aria-label", count ? `复制已选 ${count} 个 UID` : "复制 UID");
  els.next.setAttribute("aria-label", count ? `对已选 ${count} 个用户执行下一步` : "下一步");
  els.clear.setAttribute("aria-label", count ? `清除已选 ${count} 项` : "清除选择");

  const visible = filtered();
  const allSelected = visible.length > 0 && visible.every((friend) => state.selected.has(friend.uid));
  els.selectVisible.textContent = allSelected ? "取消全选" : "全选可见";
  els.selectVisible.disabled = visible.length === 0;
  els.selectVisible.setAttribute(
    "aria-label",
    allSelected ? `取消选择当前可见的 ${visible.length} 个用户` : `选择当前可见的 ${visible.length} 个用户`,
  );
}

async function copySelected() {
  if (state.selected.size === 0) {
    showToast("请先选择用户");
    return;
  }
  try {
    await navigator.clipboard.writeText([...state.selected].join("\n"));
    showToast(`已复制 ${state.selected.size} 个 UID`);
  } catch {
    showToast("复制失败，请检查浏览器权限");
  }
}

async function submit() {
  if (state.selected.size === 0) {
    showToast("请先选择用户");
    return;
  }
  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "next", uids: [...state.selected] }),
    });
    const payload = await response.json().catch(() => ({}));
    showToast(response.ok ? "任务已创建" : `尚未实现：${payload.error ?? `HTTP ${response.status}`}`);
  } catch (error) {
    showToast(`请求失败：${error.message}`);
  }
}

let toastTimer;

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.hidden = true;
  }, 2600);
}
