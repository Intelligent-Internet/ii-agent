# Scribe AI-Salon MVP - Task Plan & Token Budget

## Overview
This plan implements the Scribe AI-Salon MVP build based on II-Agent architecture with Agent-S orchestration, real-time voice interaction, and multi-LLM cognitive salon capabilities.

**Project Context**: Building a real-time multi-LLM voice-based cognitive salon leveraging II-Agent's existing infrastructure (Agent-S, multi-provider LLM support, WebSocket server, React frontend).

**Execution Order**: T1 → T3 → T4 → T5 (Tonight's schedule)
**Token Budget**: Each task block ≤60% context (~120k tokens), stop at 55-60%
**Auto-Continue**: Hooks will automatically continue to next task in queue

---

## Task Definitions

### T1: Planning & Architecture Analysis
**Status**: PLAN phase only (implementation in T1-IMPL)
**Token Budget**: ~50k tokens (25% context)
**Estimated Time**: 30-45 minutes

#### Objectives
1. Analyze existing II-Agent architecture and capabilities
2. Review Agent-S personas, orchestrator, and timeout systems
3. Map Manus/Salon reference documents to implementation
4. Design integration architecture for voice + multi-LLM
5. Create detailed technical specification

#### Key Files to Analyze
- `src/ii_agent/server/` - WebSocket server architecture
- `src/ii_agent/tools/agent_s_*.py` - Agent-S integration points
- `src/ii_agent/llm/` - Multi-provider LLM infrastructure
- `frontend/` - React UI components and WebSocket client
- `docs/AGENT_S_SUMMARY.md` - Agent-S capabilities

#### Deliverables
1. Architecture diagram (text-based)
2. Component integration map
3. API surface design for voice/salon features
4. File modification plan with dependencies
5. Risk assessment and mitigation strategies

#### Context Sources
- Obsidian: `/Users/kylemcnease/Claude-Workspace/SCRIBE AI-Salon Build/`
- Reference mirror: `reference/obsidian_mirror/`
- Key docs: Manus detailed build, agent_s_personas.md, AGENT_S_SUMMARY.md

#### Token Management
- Use targeted file reads (limit parameter)
- Leverage grep/glob for discovery
- Store findings in `.claude/notes/T1_analysis.md`
- Reference by path rather than full content

---

### T3: Voice Pipeline Integration
**Status**: Ready for implementation
**Token Budget**: ~100k tokens (50% context)
**Estimated Time**: 2-3 hours

#### Objectives
1. Implement real-time speech-to-text (STT) pipeline
2. Add text-to-speech (TTS) narrator/reader capabilities
3. Create voice session management
4. Integrate with existing WebSocket server
5. Build voice UI components

#### Implementation Plan

##### Backend Components
1. **Voice Service Module** (`src/ii_agent/voice/`)
   - `stt_service.py` - Real-time transcription (OpenAI Whisper API)
   - `tts_service.py` - Voice synthesis (OpenAI TTS API)
   - `voice_session.py` - Session state and audio stream management
   - `audio_buffer.py` - Audio chunking and buffering

2. **WebSocket Voice Handlers** (`src/ii_agent/server/`)
   - Extend `ws_server.py` with voice message types
   - Add audio stream endpoints
   - Implement voice session lifecycle

3. **Voice Tool** (`src/ii_agent/tools/`)
   - `voice_narrator_tool.py` - TTS tool for Agent-S personas
   - Integrate with agent_s_orchestrator for voice output

##### Frontend Components
4. **Voice UI** (`frontend/components/voice/`)
   - `VoiceRecorder.tsx` - Microphone capture with AudioWorklet
   - `VoiceVisualizer.tsx` - Real-time waveform display
   - `VoiceControls.tsx` - PTT, continuous, mute controls
   - `AudioPlayer.tsx` - TTS playback with queue management

5. **WebSocket Client Updates** (`frontend/lib/`)
   - Add voice message handlers
   - Implement audio stream encoding (WebM/Opus)
   - Voice session state management

##### Configuration
6. **Settings & Environment**
   - Add voice API keys to `.env` and settings schema
   - Voice quality/model configuration
   - Latency optimization flags

#### Key Dependencies
- OpenAI API (Whisper for STT, TTS for voice)
- Browser Web Audio API (MediaRecorder, AudioContext)
- WebSocket binary message support (already present)
- Agent-S orchestrator (already implemented)

#### Testing Strategy
- Unit tests for audio buffer chunking
- Integration tests for STT/TTS roundtrip
- Manual testing with voice UI
- Latency benchmarking (<500ms target)

#### Token Management
- Implement core voice service first (~30k)
- Add WebSocket integration (~25k)
- Build frontend components (~35k)
- Testing and refinement (~10k)

---

### T4: Safe Mode & Registry System
**Status**: Ready for implementation
**Token Budget**: ~80k tokens (40% context)
**Estimated Time**: 1.5-2 hours

#### Objectives
1. Implement permission/capability registry
2. Create safe mode execution sandbox
3. Add tool authorization framework
4. Build UI for permission management
5. Integrate with Agent-S personas

#### Implementation Plan

##### Backend Components
1. **Registry System** (`src/ii_agent/core/registry/`)
   - `capability_registry.py` - Tool capability definitions
   - `permission_manager.py` - User permission checks
   - `safe_mode_config.py` - Safe mode profiles (read-only, restricted, full)
   - `audit_logger.py` - Action logging and history

2. **Tool Authorization** (`src/ii_agent/tools/`)
   - Update `base.py` with authorization decorators
   - Add permission checks to all tools
   - Create `restricted_tool_wrapper.py` for safe mode

3. **Database Schema** (`src/ii_agent/db/`)
   - Add permissions table migration
   - User capability associations
   - Audit log table

##### Frontend Components
4. **Permission UI** (`frontend/components/settings/`)
   - `PermissionsPanel.tsx` - Permission matrix display
   - `SafeModeToggle.tsx` - Quick safe mode switch
   - `CapabilityManager.tsx` - Grant/revoke capabilities
   - `AuditLog.tsx` - Action history viewer

5. **Tool Execution UI**
   - Permission prompt dialogs
   - Confirmation for destructive actions
   - Real-time capability status indicators

##### Integration Points
6. **Agent-S Integration**
   - Update personas to respect safe mode
   - Add permission checks to orchestrator
   - Tool filtering based on active capabilities

7. **WebSocket Updates**
   - Permission request/response messages
   - Real-time capability updates
   - Safe mode status broadcasting

#### Safe Mode Profiles
- **Read-Only**: File read, web search, analysis only
- **Restricted**: + File write (with approval), safe tool execution
- **Full**: All capabilities (production mode)

#### Token Management
- Registry implementation (~25k)
- Tool authorization layer (~20k)
- Frontend UI (~25k)
- Integration and testing (~10k)

---

### T5: Multi-LLM Salon Orchestration
**Status**: Ready for implementation
**Token Budget**: ~100k tokens (50% context)
**Estimated Time**: 2-3 hours

#### Objectives
1. Create cognitive salon conversation framework
2. Implement multi-LLM turn-taking orchestration
3. Add debate/discussion/consensus modes
4. Build salon UI with participant tracking
5. Integrate voice for each LLM persona

#### Implementation Plan

##### Backend Components
1. **Salon Orchestrator** (`src/ii_agent/salon/`)
   - `salon_manager.py` - Conversation state machine
   - `turn_coordinator.py` - LLM turn scheduling (round-robin, priority, debate)
   - `consensus_engine.py` - Agreement detection and synthesis
   - `salon_personas.py` - Predefined salon participant roles

2. **Multi-LLM Handler** (`src/ii_agent/llm/`)
   - Update `__init__.py` for parallel LLM invocation
   - Add model pooling and load balancing
   - Implement streaming response merging

3. **Salon Tool** (`src/ii_agent/tools/`)
   - `salon_orchestrator_tool.py` - Main salon execution tool
   - Integrates with Agent-S orchestrator
   - Voice output per participant

##### Frontend Components
4. **Salon UI** (`frontend/components/salon/`)
   - `SalonView.tsx` - Multi-column conversation display
   - `ParticipantCard.tsx` - LLM persona with avatar/voice indicator
   - `ConversationFlow.tsx` - Turn-by-turn discussion visualization
   - `SalonControls.tsx` - Mode selection, add/remove participants
   - `ConsensusIndicator.tsx` - Real-time agreement tracking

5. **Salon Session Management**
   - `SalonSessionProvider.tsx` - React context for salon state
   - WebSocket salon message handlers
   - Participant voice assignment

##### Conversation Modes
6. **Mode Implementations**
   - **Debate**: Adversarial positions, moderated turns
   - **Discussion**: Collaborative exploration, free-form turns
   - **Panel**: Expert Q&A with moderator routing
   - **Consensus**: Agreement-seeking with synthesis

##### Integration
7. **Voice + Salon**
   - Assign unique TTS voices to each participant
   - Voice turn indicators in UI
   - Audio mixing for overlapping thoughts

8. **Agent-S + Salon**
   - Salon as orchestrator meta-mode
   - Agent-S personas as salon participants
   - Tool execution within salon context

#### Salon Configuration
- Participant roles (Researcher, Critic, Designer, etc.)
- Turn duration and interruption rules
- Consensus threshold and voting
- Voice mapping to personas

#### Token Management
- Core salon orchestrator (~35k)
- Multi-LLM coordination (~25k)
- Frontend salon UI (~30k)
- Integration and testing (~10k)

---

## Execution Protocol

### Auto-Continue System
The `.claude/hooks/continue_next_task.py` hook automatically:
1. Detects task completion
2. Updates `task_queue.json` cursor
3. Initiates next task without user intervention

### Token Budget Discipline
- Monitor token usage via `<system_warning>` tags
- Stop at 55-60% context (~110-120k tokens)
- Create continuation notes in `.claude/notes/`
- Next session resumes from queue cursor

### Path Validation
All writes validated by `.claude/hooks/validate_write_paths.py`:
- Writes must stay inside `$CLAUDE_PROJECT_DIR`
- `reference/` is read-only (copy to workspace first)
- Obsidian writes restricted to `/Phase 5/` path

### Quality Gates
Each task must produce:
1. ✅ Working code (no syntax errors)
2. ✅ Updated documentation
3. ✅ Test coverage (where applicable)
4. ✅ Integration validation
5. ✅ Continuation notes for next task

---

## Reference Materials

### Critical Documents
Located in `reference/obsidian_mirror/` (to be populated):
- `ai-salon-mvp.tar.gz` - Complete project context
- `Manus Detailed Build Breakdown.txt` - Step-by-step implementation
- `ai_salon_ai_narrator_reader_tts_one_shot_build_plan.md` - Voice architecture
- `Designing a Real-Time Multi-LLM Voice-Based Cognitive Salon.pdf` - System design
- `Manus AI Forensic Research.md` - Technical research
- `Cognitive Salon Engineering Dossier.pdf` - Engineering specs
- Design mockups: `cbfd59a5-*.png`, `2a90b8fc-*.png`, etc.

### Existing Codebase Assets
- Agent-S personas and orchestrator (fully implemented)
- Multi-provider LLM support (Anthropic, OpenAI, Gemini, xAI)
- WebSocket server with streaming responses
- React frontend with Monaco editor
- Docker containerization
- Settings management system

---

## Risk Mitigation

### High-Risk Areas
1. **Voice Latency**: Target <500ms STT+TTS roundtrip
   - Mitigation: Streaming APIs, audio buffering, pre-warm connections

2. **Multi-LLM Rate Limits**: Concurrent API calls may hit limits
   - Mitigation: Request queuing, exponential backoff, model pooling

3. **WebSocket Stability**: High-frequency audio messages
   - Mitigation: Binary encoding, compression, heartbeat monitoring

4. **UI Performance**: Real-time updates from multiple sources
   - Mitigation: React.memo, virtual scrolling, debounced renders

### Medium-Risk Areas
- Safe mode bypass vulnerabilities
- Permission escalation paths
- Audio codec compatibility (browser-specific)
- Token context management at scale

---

## Success Criteria

### T1 (Planning)
- [ ] Complete architecture document
- [ ] All integration points identified
- [ ] Risk assessment completed
- [ ] Implementation roadmap approved

### T3 (Voice)
- [ ] STT working with <500ms latency
- [ ] TTS generating natural speech
- [ ] Voice UI functional in browser
- [ ] WebSocket audio streaming stable

### T4 (Safe Mode)
- [ ] Permission system preventing unauthorized actions
- [ ] Safe mode profiles enforced
- [ ] UI showing capability status
- [ ] Audit log capturing all actions

### T5 (Salon)
- [ ] Multi-LLM conversation flowing
- [ ] Turn-taking coordinated properly
- [ ] Voice assigned to each participant
- [ ] UI showing conversation state
- [ ] Consensus detection working

---

## Notes for Continuation

Each task creates `/Users/kylemcnease/Claude-Workspace/SCRIBE AI-Salon Build/Phase 5/[Task]_notes.md` with:
- Implementation progress
- Outstanding issues
- Next steps
- Code snippets for reference
- Token budget remaining

This allows seamless continuation across auto-resume boundaries.

---

**Current Status**: Planning phase - T1 execution ready
**Next Action**: Analyze existing codebase and design integration architecture
**Token Budget**: 52.5k/200k used (26.25%)
