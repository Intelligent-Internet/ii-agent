import { combineReducers } from 'redux'
import { messagesReducer } from './slice/messages'
import { contextReducer } from './slice/context'
import { uiReducer } from './slice/ui'
import { editorReducer } from './slice/editor'
import { agentReducer } from './slice/agent'
import { filesReducer } from './slice/files'
import { workspaceReducer } from './slice/workspace'
import { settingsReducer } from './slice/settings'
import { sessionsReducer } from './slice/sessions'
import { userReducer } from './slice/user'
import { favoritesReducer } from './slice/favorites'
import { userApi } from './api/user.api'
import { sessionApi } from './api/session.api'

export default combineReducers({
    messages: messagesReducer,
    ui: uiReducer,
    editor: editorReducer,
    agent: agentReducer,
    files: filesReducer,
    workspace: workspaceReducer,
    context: contextReducer,
    settings: settingsReducer,
    sessions: sessionsReducer,
    user: userReducer,
    favorites: favoritesReducer,
    [userApi.reducerPath]: userApi.reducer,
    [sessionApi.reducerPath]: sessionApi.reducer
})
