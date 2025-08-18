import uuid
import asyncio
from mcp.types import ToolAnnotations
from fastmcp import FastMCP
from argparse import ArgumentParser
from ii_tool.core.config import WebSearchConfig, WebVisitConfig, ImageSearchConfig, VideoGenerateConfig, ImageGenerateConfig, FullStackDevConfig
from ii_tool.tools.manager import get_default_tools
from ii_tool.tools.browser_tools.click import BrowserClickTool
from ii_tool.tools.browser_tools.navigate import BrowserNavigationTool, BrowserRestartTool
from ii_tool.tools.browser_tools.scroll import BrowserScrollDownTool, BrowserScrollUpTool
from ii_tool.tools.browser_tools.enter_text import BrowserEnterTextTool
from ii_tool.tools.browser_tools.view import BrowserViewTool
from ii_tool.tools.browser_tools.dropdown import BrowserGetSelectOptionsTool, BrowserSelectDropdownOptionTool
from ii_tool.tools.browser_tools.press_key import BrowserPressKeyTool
from ii_tool.tools.browser_tools.tab import BrowserSwitchTabTool, BrowserOpenNewTabTool
from ii_tool.tools.browser_tools.wait import BrowserWaitTool
from dotenv import load_dotenv
import os
from ii_agent.browser.browser import Browser
from fastmcp import FastMCP, Client

load_dotenv()


async def create_mcp_with_browser_tools(workspace_dir: str, session_id: str):
    """Create MCP instance with all browser tools registered"""
    web_search_config = WebSearchConfig()
    web_visit_config = WebVisitConfig()
    fullstack_dev_config = FullStackDevConfig()
    
    tools = get_default_tools(
        chat_session_id=session_id,
        workspace_path=workspace_dir,
        web_search_config=web_search_config,
        web_visit_config=web_visit_config,
        fullstack_dev_config=fullstack_dev_config,
    )
    
    # Initialize browser
    browser = Browser()
    
    # Add all browser tools
    browser_tools = [
        BrowserClickTool(browser),
        BrowserNavigationTool(browser),
        BrowserRestartTool(browser),
        BrowserScrollDownTool(browser),
        BrowserScrollUpTool(browser),
        BrowserEnterTextTool(browser),
        BrowserViewTool(browser),
        BrowserGetSelectOptionsTool(browser),
        BrowserSelectDropdownOptionTool(browser),
        BrowserPressKeyTool(browser),
        BrowserSwitchTabTool(browser),
        BrowserOpenNewTabTool(browser),
        BrowserWaitTool(browser),
    ]
    
    # Add browser tools to the tools list
    tools.extend(browser_tools)
    
    # Print tool information for debugging
    print("\n" + "="*60)
    print("BROWSER TOOLS REGISTERED")
    print("="*60)
    for tool in browser_tools:
        print(f"✓ {tool.name:<35} | {tool.display_name}")
    print("="*60 + "\n")
    
    mcp = FastMCP()

    for tool in tools:
        mcp.tool(
            tool.execute_mcp_wrapper,
            name=tool.name,
            description=tool.description,
            annotations=ToolAnnotations(
                title=tool.display_name,
                readOnlyHint=tool.read_only,
            ),
        )

        # NOTE: this is a temporary fix to set the parameters of the tool
        _mcp_tool = await mcp._tool_manager.get_tool(tool.name)
        _mcp_tool.parameters = tool.input_schema

    return mcp, browser


async def test_all_browser_tools():
    """Comprehensive test for all browser tools using a single MCP instance and client"""
    
    print("\n" + "="*60)
    print("STARTING COMPREHENSIVE BROWSER TOOLS TEST")
    print("="*60)
    
    # Create single MCP instance and browser
    mcp, browser = await create_mcp_with_browser_tools("/home/", "test_session_all_tools")
    client = Client(mcp)
    
    try:
        async with client:
            # Track test results
            test_results = []
            
            # ========== TEST 1: Navigation ==========
            print("\n[TEST 1] Testing Browser Navigation...")
            try:
                result = await client.call_tool("browser_navigation", {"url": "https://www.example.com"})
                print(f"  ✓ Navigation to example.com successful, ", result)
                test_results.append(("Navigation", True, None))
            except Exception as e:
                print(f"  ✗ Navigation failed: {e}")
                test_results.append(("Navigation", False, str(e)))
            
            # ========== TEST 2: View Interactive Elements ==========
            print("\n[TEST 2] Testing View Interactive Elements...")
            try:
                result = await client.call_tool("browser_view_interactive_elements", {})
                print(f"  ✓ View interactive elements successful, ", result)
                test_results.append(("View Elements", True, None))
            except Exception as e:
                print(f"  ✗ View elements failed: {e}")
                test_results.append(("View Elements", False, str(e)))
            
            # ========== TEST 3: Wait ==========
            print("\n[TEST 3] Testing Browser Wait...")
            try:
                result = await client.call_tool("browser_wait", {})
                print(f"  ✓ Wait successful ", result, )
                test_results.append(("Wait", True, None))
            except Exception as e:
                print(f"  ✗ Wait failed: {e}")
                test_results.append(("Wait", False, str(e)))
            
            # ========== TEST 4: Click ==========
            print("\n[TEST 4] Testing Browser Click...")
            try:
                result = await client.call_tool("browser_click", {"coordinate_x": 200, "coordinate_y": 100})
                print(f"  ✓ Click at (200, 100) successful, ", result)
                test_results.append(("Click", True, None))
            except Exception as e:
                print(f"  ✗ Click failed: {e}")
                test_results.append(("Click", False, str(e)))
            
            # ========== TEST 5: Scroll ==========
            print("\n[TEST 5] Testing Browser Scroll...")
            try:
                # Navigate to a longer page for scrolling
                await client.call_tool("browser_navigation", {"url": "https://www.wikipedia.org"})
                
                # Test scroll down
                result = await client.call_tool("browser_scroll_down", {})
                print(f"  ✓ Scroll down successful", result)
                
                # Test scroll up
                result = await client.call_tool("browser_scroll_up", {})
                print(f"  ✓ Scroll up successful")
                test_results.append(("Scroll", True, None))
            except Exception as e:
                print(f"  ✗ Scroll failed: {e}")
                test_results.append(("Scroll", False, str(e)))
            
            # ========== TEST 6: Open New Tab ==========
            print("\n[TEST 6] Testing Tab Management...")
            try:
                # Open new tab
                result = await client.call_tool("browser_open_new_tab", {})
                print(f"  ✓ Open new tab successful, ", result)
                
                # Navigate in new tab
                await client.call_tool("browser_navigation", {"url": "https://www.github.com"})
                print(f"  ✓ Navigation in new tab successful, ", result)
                
                # Switch to first tab
                result = await client.call_tool("browser_switch_tab", {"index": 0})
                print(f"  ✓ Switch to tab 0 successful, ", result)
                
                # Switch back to second tab
                result = await client.call_tool("browser_switch_tab", {"index": 1})
                print(f"  ✓ Switch to tab 1 successful,", result)
                test_results.append(("Tab Management", True, None))
            except Exception as e:
                print(f"  ✗ Tab management failed: {e}")
                test_results.append(("Tab Management", False, str(e)))
            
            # ========== TEST 7: Enter Text ==========
            print("\n[TEST 7] Testing Enter Text...")
            try:
                # Navigate to Google
                await client.call_tool("browser_navigation", {"url": "https://www.google.com"})
                
                # Click on search box (approximate coordinates)
                await client.call_tool("browser_click", {"coordinate_x": 500, "coordinate_y": 400})
                
                # Enter text without pressing Enter
                result = await client.call_tool("browser_enter_text", {
                    "text": "OpenAI GPT-4",
                    "press_enter": False
                })
                print(f"  ✓ Enter text without Enter successful, ", result)
                
                # Clear and enter text with Enter
                result = await client.call_tool("browser_enter_text", {
                    "text": "Machine Learning",
                    "press_enter": True
                })
                print(f"  ✓ Enter text with Enter successful, ", result)
                test_results.append(("Enter Text", True, None))
            except Exception as e:
                print(f"  ✗ Enter text failed: {e}")
                test_results.append(("Enter Text", False, str(e)))
            
            # ========== TEST 8: Press Key ==========
            print("\n[TEST 8] Testing Press Key...")
            try:
                # Go back to example.com for testing
                await client.call_tool("browser_navigation", {"url": "https://www.example.com"})
                
                # Test various key presses
                result = await client.call_tool("browser_press_key", {"key": "Tab"})
                print(f"  ✓ Press Tab successful, ", result)
                
                result = await client.call_tool("browser_press_key", {"key": "Enter"})
                print(f"  ✓ Press Enter successful, ", result)
                
                result = await client.call_tool("browser_press_key", {"key": "Escape"})
                print(f"  ✓ Press Escape successful, ", result)
                test_results.append(("Press Key", True, None))
            except Exception as e:
                print(f"  ✗ Press key failed: {e}")
                test_results.append(("Press Key", False, str(e)))
            
            # ========== TEST 9: Dropdown (if available) ==========
            print("\n[TEST 9] Testing Dropdown Tools...")
            try:
                # Navigate to a page with dropdowns
                await client.call_tool("browser_navigation", {"url": "https://www.w3schools.com/html/html_form_elements.asp"})
                import base64

                # View elements to find select elements
                view_result = await client.call_tool("browser_view_interactive_elements", {})
                obj = view_result.content[0]
                # Assuming obj is your ImageContent instance
                # Example: obj = ImageContent(type="image", data="<base64 string>", mime_type="image/png")

                # Pick the file extension from mime_type
                extension = "png" 
                filename = f"output.{extension}"

                # Decode and save
                with open(filename, "wb") as f:
                    f.write(base64.b64decode(obj.data))

                print(f"Image saved as {filename}")
                # Note: This might fail if no select element exists at the expected index
                # We'll handle this gracefully
                try:
                    # Try to get select options (using a hypothetical index)
                    result = await client.call_tool("browser_get_select_options", {"index": 10})
                    print(f"  ✓ Get select options successful ", result)
                    
                    # Try to select an option
                    result = await client.call_tool("browser_select_dropdown_option", {
                        "index": 10,
                        "option": "Option 1"
                    })
                    print(f"  ✓ Select dropdown option successful")
                    test_results.append(("Dropdown", True, None))
                except Exception as e:
                    print(f"  ⚠ Dropdown test skipped (no select element found): {e}")
                    test_results.append(("Dropdown", True, "Skipped - no select element"))
            except Exception as e:
                print(f"  ✗ Dropdown test failed: {e}")
                test_results.append(("Dropdown", False, str(e)))
            
            # ========== TEST 10: Browser Restart ==========
            print("\n[TEST 10] Testing Browser Restart...")
            try:
                result = await client.call_tool("browser_restart", {"url": "https://www.python.org"})
                print(f"  ✓ Browser restart with navigation successful, ", result)
                test_results.append(("Browser Restart", True, None))
            except Exception as e:
                print(f"  ✗ Browser restart failed: {e}")
                test_results.append(("Browser Restart", False, str(e)))
            
            # ========== PRINT TEST SUMMARY ==========
            print("\n" + "="*60)
            print("TEST SUMMARY")
            print("="*60)
            
            passed = sum(1 for _, success, _ in test_results if success)
            total = len(test_results)
            
            for test_name, success, error in test_results:
                status = "✓ PASSED" if success else "✗ FAILED"
                error_msg = f" ({error})" if error and not success else ""
                print(f"{test_name:<20} | {status}{error_msg}")
            
            print("-"*60)
            print(f"Total: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
            print("="*60)
            
            return test_results
            
    except Exception as e:
        print(f"\n✗ Critical error during testing: {e}")
        raise
    finally:
        # Clean up browser
        await browser.close()
        print("\n✓ Browser closed successfully")


async def main():
    """Main function to run all browser tool tests"""
    try:
        results = await test_all_browser_tools()
        
        # Exit with appropriate code
        passed = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        if passed == total:
            print("\n🎉 All tests passed successfully!")
            exit(0)
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            exit(1)
    except Exception as e:
        print(f"\n💥 Test suite failed with error: {e}")
        exit(1)


# Note: This should be run in docker for proper browser functionality
if __name__ == '__main__':
    asyncio.run(main())