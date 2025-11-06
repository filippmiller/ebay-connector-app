# Git Workflow - Feature Branches & PRs

**Last Updated:** 2025-11-06

---

## Workflow для больших изменений

### Правило:
**Для больших изменений (новые фичи, рефакторинг, множественные файлы) использовать feature branches и Pull Requests.**

### Процесс:

1. **Создать feature branch:**
   ```bash
   git checkout -b feature/inventory-offers-sync
   # или
   git checkout -b fix/login-timeout
   ```

2. **Делать изменения в feature branch:**
   - Коммитить по мере готовности
   - Тестировать локально если возможно

3. **Push feature branch:**
   ```bash
   git push origin feature/inventory-offers-sync
   ```

4. **Создать Pull Request на GitHub:**
   - Описать изменения
   - Указать что тестировать
   - Попросить review (если есть)

5. **После review и тестирования - merge в main:**
   - Merge через GitHub UI
   - Или через `git merge` локально

6. **Если что-то сломалось - легко откатить:**
   ```bash
   git revert <commit-hash>
   # или
   git reset --hard <commit-before-feature>
   ```

---

## Когда использовать feature branch:

✅ **Использовать feature branch:**
- Новые фичи (inventory sync, offers sync)
- Большие рефакторинги
- Изменения в 3+ файлах
- Изменения, которые могут сломать существующий функционал
- Изменения, требующие тестирования перед merge

❌ **Можно коммитить напрямую в main:**
- Мелкие багфиксы (1-2 строки)
- Обновление документации
- Исправление опечаток
- Изменения, которые точно не сломают ничего

---

## Naming Conventions:

- `feature/` - новые фичи (feature/inventory-sync)
- `fix/` - багфиксы (fix/login-timeout)
- `refactor/` - рефакторинг (refactor/ebay-service)
- `docs/` - документация (docs/api-documentation)

---

## Пример для текущей ситуации:

Если бы мы делали inventory/offers sync сейчас:

```bash
# 1. Создать branch
git checkout -b feature/inventory-offers-sync

# 2. Делать изменения и коммитить
git add backend/app/services/ebay.py
git commit -m "Add fetch_inventory_items method"
# ... и т.д.

# 3. Push branch
git push origin feature/inventory-offers-sync

# 4. Создать PR на GitHub
# - Title: "Implement inventory and offers sync"
# - Description: описать изменения, что тестировать

# 5. После тестирования - merge в main
# 6. Если что-то сломалось - легко откатить PR
```

---

## Преимущества:

1. **Легкий откат** - можно просто закрыть PR или revert merge
2. **Review** - можно проверить изменения перед merge
3. **Тестирование** - можно протестировать в изоляции
4. **История** - понятно что и когда было добавлено
5. **Безопасность** - main всегда в рабочем состоянии

---

## Для текущего проекта:

**Рекомендация:** Использовать feature branches для:
- Новых sync операций
- Изменений в auth/login
- Изменений в database migrations
- Больших рефакторингов

**Можно коммитить в main:**
- Мелкие багфиксы
- Обновление документации
- Исправление опечаток


